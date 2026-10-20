"""本地冻结测试数据的固定身份、无损解压与导出；不联网或执行测试代码。"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from importlib.resources import files
from pathlib import Path

from .util import KSEOError, confined, digest, write_json


def catalog() -> list[dict]:
    return json.loads(files('kseo').joinpath('data/datasets.json').read_text(encoding='utf-8'))['datasets']


def load_dataset(name: str) -> dict:
    entry = next((entry for entry in catalog() if entry['id'] == name), None)
    if entry is None:
        raise KSEOError(f'没有登记该数据集：{name}')
    return entry


def _source(entry: dict, row: dict, root: Path | None):
    if root is not None:
        return confined(root, row['filename'])
    if entry['distribution'] != 'bundled':
        raise KSEOError(f"{entry['id']} 的正文未随包分发；使用 --root 指向本地冻结文件目录")
    return files('kseo').joinpath('data/' + row['path'])


def verify(name: str, root: Path | None = None) -> dict:
    entry = load_dataset(name)
    assembled = entry.get('assembled_file')
    use_original = assembled is not None and root is not None and confined(root, assembled['filename']).is_file()
    rows_to_check = [assembled] if use_original else entry['files']
    checked = []
    ids = []
    content_hashes = set()
    combined = hashlib.sha256()
    combined_bytes = combined_records = 0

    def record(item):
        if not isinstance(item, dict):
            raise KSEOError('数据记录必须是 JSON 对象')
        if entry.get('id_field'):
            sample_id = item.get(entry['id_field'])
            if not isinstance(sample_id, str) or not sample_id:
                raise KSEOError('数据 sample ID 缺失')
            ids.append(sample_id)
            if entry.get('unique_contents') is not None:
                value = {k: v for k, v in item.items() if k != entry['id_field']}
                content_hashes.add(digest(value))

    def consume(stream, fmt, hashing=False):
        nonlocal combined_bytes
        local = hashlib.sha256()
        length = 0
        def count_bytes(blob):
            nonlocal combined_bytes, length
            length += len(blob)
            local.update(blob)
            if hashing:
                combined.update(blob)
                combined_bytes += len(blob)
        if fmt == 'jsonl':
            count = 0
            for line in stream:
                count_bytes(line)
                if line.strip():
                    record(json.loads(line)); count += 1
        else:
            blob = stream.read(); count_bytes(blob)
            value = json.loads(blob)
            if fmt == 'json_array':
                if not isinstance(value, list):
                    raise KSEOError('数据要求 JSON 数组')
                for item in value:
                    record(item)
                count = len(value)
            else:
                count = 1
        return count, length, local.hexdigest()

    for row in rows_to_check:
        source = _source(entry, row, root)
        h = hashlib.sha256(); size = 0
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(chunk); h.update(chunk)
        if size != row['bytes'] or h.hexdigest() != row['sha256']:
            raise KSEOError(f"数据文件身份不匹配：{row['filename']}")
        count = None
        if row['format'] == 'gzip_part':
            with source.open('rb') as raw, gzip.GzipFile(fileobj=raw) as stream:
                count, length, actual = consume(stream, assembled['format'], hashing=True)
            if length != row['uncompressed_bytes'] or actual != row['uncompressed_sha256']:
                raise KSEOError('gzip 分片解压后身份不符')
            combined_records += count
        elif row['format'] in ('jsonl', 'json_array', 'json'):
            with source.open('rb') as stream:
                count, _, _ = consume(stream, row['format'])
        if row.get('records') is not None and count != row['records']:
            raise KSEOError(f"数据记录数不匹配：{row['filename']}")
        checked.append({'filename':row['filename'],'sha256':h.hexdigest(),'bytes':size,'records':count})
    if assembled and not use_original:
        if (combined_bytes != assembled['bytes'] or combined.hexdigest() != assembled['sha256']
                or combined_records != assembled['records']):
            raise KSEOError('拼接解压结果与本地原始数据文件不一致')
    if ids and (len(ids) != len(set(ids)) or (entry.get('ordered_sample_ids') is not None and ids != entry['ordered_sample_ids'])):
        raise KSEOError('数据 ID 缺失、重复或顺序与本地冻结清单不符')
    if entry.get('unique_contents') is not None and len(content_hashes) != entry['unique_contents']:
        raise KSEOError('去掉 ID 后的内容数量与已披露本地快照不符；不能自行去重或换集')
    return {'dataset':name,'dataset_manifest_sha256':digest(entry),'distribution':entry['distribution'],
            'verified':True,'files':checked,'unique_ids':len(ids),'unique_contents':len(content_hashes),
            'assembled_original_sha256':assembled['sha256'] if assembled else None,
            'note':'仅证明本地数据身份和结构，不代表执行过模型评测或通过精度门禁。'}


def export(name: str, output: Path) -> dict:
    entry = load_dataset(name)
    if entry['distribution'] != 'bundled':
        raise KSEOError('该数据正文不随包分发；通过 --root 核对本地原文件，不联网替换来源')
    verify(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir()
    except FileExistsError as exc:
        raise KSEOError('数据导出目录已存在，拒绝覆盖') from exc
    try:
        assembled = entry.get('assembled_file')
        destination = confined(output, assembled['filename']) if assembled else None
        if destination:
            with destination.open('wb') as dst:
                for row in entry['files']:
                    if row['format'] == 'gzip_part':
                        with _source(entry,row,None).open('rb') as raw, gzip.GzipFile(fileobj=raw) as src:
                            shutil.copyfileobj(src,dst)
        for row in entry['files']:
            if row['format'] == 'gzip_part':
                continue
            with _source(entry,row,None).open('rb') as src, confined(output,row['filename']).open('wb') as dst:
                shutil.copyfileobj(src,dst)
        result = verify(name,output)
        write_json(output/'dataset.json',entry)
        return result
    except BaseException:
        shutil.rmtree(output)
        raise
