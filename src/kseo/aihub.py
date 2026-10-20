"""AIHub stdlib client：真实 REST 接口与按 run/trial 归属的任务创建、恢复和停止。"""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .util import KSEOError, digest, positive_int, read_json, write_json

BASE = '/model-training-platform/api/v1'


class HTTPFailure(KSEOError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'AIHub HTTP {status}；响应正文未写入日志，避免泄漏凭据')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KSEOError('AIHub API 重定向被拒绝，不能向另一地址转发凭据')


def read_token(path):
    raw = Path(path).read_text().strip()
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get('token'), str):return value['token']
    except ValueError:
        pass
    tokens = set(re.findall(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', raw))
    if len(tokens) == 1:return tokens.pop()
    if len(raw.splitlines()) == 1 and not re.search(r'\s', raw) and len(raw) > 16:return raw
    raise KSEOError('无法唯一读取 token；使用纯 token 文件、含 token 字段的 JSON 或单个 JWT；内容未输出')


class Client:
    def __init__(self, url, token, timeout=30):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise KSEOError('AIHub URL 必须为无 credentials/query 的明确 HTTP(S) 基址')
        if not isinstance(token,str) or not token or '\n' in token or '\r' in token:
            raise KSEOError('AIHub token 无效')
        self.url=url.rstrip('/');self.token=token;self.timeout=timeout
        self.opener=urllib.request.build_opener(NoRedirect)

    def request(self, method, path, payload=None, query=None):
        if not path.startswith((BASE+'/', '/quota-schedule-management/api/v1/')) or '..' in path:
            raise KSEOError('拒绝不属于已登记 AIHub API 的路径')
        url=self.url+path
        if query:url+='?'+urllib.parse.urlencode(query)
        body=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
        request=urllib.request.Request(url,data=body,method=method,headers={
            'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=self.timeout) as response:data=json.load(response)
        except urllib.error.HTTPError as exc:raise HTTPFailure(exc.code) from None
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise KSEOError('AIHub 传输失败：'+type(exc).__name__+'；不自动重试创建请求') from None
        if not isinstance(data,dict) or data.get('code') != 0 or 'data' not in data:
            raise KSEOError('AIHub 返回无效 wrapper 或非零 code；原始正文不进入异常')
        return data['data']

    def storages(self):return self.request('GET',BASE+'/storages')
    def trainings(self, **query):return self.request('GET',BASE+'/trainings',query=query)
    def training(self, identifier):
        return self.request('GET',BASE+f'/trainings/{positive_int(identifier,"training_id")}')
    def pods(self, identifier):return self.request('GET',BASE+f'/trainings/{positive_int(identifier,"training_id")}/pods')
    def pod_detail(self, identifier, pod, kind):
        if kind not in ('spec','events','logs/new'):raise KSEOError('未知 Pod 诊断类型')
        return self.request('GET',BASE+f'/trainings/{positive_int(identifier,"training_id")}/pods/{positive_int(pod,"pod_id")}/{kind}')
    def metrics(self, **query):return self.request('GET','/quota-schedule-management/api/v1/metrics/overview',query=query)

    def launch(self, payload, *, owner, ledger, cluster_id, max_gpus, max_nodes, gpus_per_sku):
        """仅创建当前任务；未确定的请求保持 UNKNOWN，不能盲目重复 POST。"""
        positive_int(cluster_id,'cluster_id');positive_int(max_gpus,'max_gpus');positive_int(max_nodes,'max_nodes')
        count=positive_int(payload.get('sku_cnt'),'sku_cnt')
        nodes=positive_int(payload.get('instances'),'instances')
        per_sku=positive_int(gpus_per_sku,'已探测 gpus_per_sku')
        if nodes > max_nodes or count*nodes*per_sku > max_gpus or payload.get('virtual_cluster_id') != cluster_id:
            raise KSEOError('AIHub 请求超出冻结集群/GPU/节点上限')
        if not isinstance(owner,str) or not owner:raise KSEOError('必须声明稳定的 run/trial owner')
        wanted=dict(payload);wanted['name']='kseo-'+digest(owner)[:24]
        wanted['description']='KSEO owner '+digest(owner)
        wanted_hash=digest(wanted)
        if ledger.exists():
            saved=read_json(ledger)
            if saved.get('owner') != owner or saved.get('payload_sha256') != wanted_hash:
                raise KSEOError('AIHub ledger 已属于其他 owner 或不同冻结请求')
            if saved.get('training_id') and saved.get('state') not in ('STOPPED',):
                self.assert_owned(saved);return saved['training_id']
            raise KSEOError('该 ledger 已停止或创建结果未知；先按精确归属核对，不重复创建')
        state={'owner':owner,'name':wanted['name'],'description':wanted['description'],'payload_sha256':wanted_hash,'state':'CREATING'}
        write_json(ledger,state)
        try:
            result=self.request('POST',BASE+'/trainings',wanted)
            identifier=positive_int(result.get('id'),'AIHub created id')
        except BaseException:
            state['state']='UNKNOWN';write_json(ledger,state);raise
        state.update(training_id=identifier,state='CREATED');write_json(ledger,state)
        self.assert_owned(state)
        return identifier

    def assert_owned(self, state):
        actual=self.training(state['training_id'])
        if actual.get('name') != state.get('name') or actual.get('description') != state.get('description'):
            raise KSEOError('远端任务归属与 ledger 不符，拒绝操作')
        return actual

    def stop(self, ledger, owner):
        state=read_json(ledger)
        if state.get('owner') != owner:raise KSEOError('不能停止其他 owner 的任务')
        if state.get('state') == 'STOPPED':return
        if not state.get('training_id'):raise KSEOError('创建状态未知，先核对远端任务，不能猜 ID 清理')
        try:self.assert_owned(state)
        except HTTPFailure as exc:
            if exc.status != 404:raise
        else:self.request('POST',BASE+f"/trainings/{state['training_id']}/stop")
        state['state']='STOPPED';write_json(ledger,state)
