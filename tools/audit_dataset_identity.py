"""仅审计 JSON 数组身份与非 ID 内容重复；不打印样本正文。"""

import argparse
from collections import Counter
from pathlib import Path

from kseo.util import digest, file_digest, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--id-field", default="_id")
    args = parser.parse_args()
    rows = read_json(args.path)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        parser.error("输入必须是 JSON 对象数组")
    content = Counter(digest({k: v for k, v in row.items() if k != args.id_field}) for row in rows)
    import json
    print(json.dumps({"source_sha256": file_digest(args.path), "rows": len(rows),
                      "unique_ids": len({row.get(args.id_field) for row in rows}),
                      "unique_non_id_records": len(content),
                      "multiplicity_histogram": dict(Counter(content.values()))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
