"""真实流式 HTTP benchmark adapter，适配 OpenAI-compatible Chat Completions。"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .adapter import emit
from .util import KSEOError, read_json


def measure(request: dict, case_id: str, endpoint: str, *, api_key: str = "", timeout: float = 600) -> dict:
    payload = dict(request["payload"])
    # 保留模型、thinking、tools、采样等负载内容，显式要求实际 usage。
    payload["stream"] = True
    payload["stream_options"] = {**payload.get("stream_options", {}), "include_usage": True}
    headers = {"Content-Type": "application/json", "X-Request-Id": request["request_id"]}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    body = json.dumps(payload, ensure_ascii=False).encode()
    message = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    start = time.perf_counter()
    first = None
    last = None
    usage = None
    done = False
    with urllib.request.urlopen(message, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                done = True
                break
            item = json.loads(data)
            if item.get("error"):
                raise KSEOError("服务端在 SSE 中返回 error")
            if item.get("usage"):
                usage = item["usage"]
            generated = False
            for choice in item.get("choices", []):
                delta = choice.get("delta", {})
                if any(delta.get(key) for key in ("content", "reasoning_content", "reasoning", "tool_calls")):
                    generated = True
            if generated:
                last = time.perf_counter()
                if first is None:
                    first = last
    if not done or first is None or last is None or not usage:
        raise KSEOError("缺少完整 SSE、生成内容或实际 usage，不能验收")
    details = usage.get("prompt_tokens_details", {}) or {}
    cached = details.get("cached_tokens", usage.get("prompt_cache_hit_tokens"))
    if cached is None:
        raise KSEOError("服务端未提供 cache read 证据；请启用对应 usage 字段")
    return {"request_id": request["request_id"], "case_id": case_id, "status": "completed",
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "cache_read_tokens": cached, "ttft_ms": (first - start) * 1000, "total_ms": (last - start) * 1000}


def main() -> None:
    if os.environ.get("KSEO_MODE") != "measured" or os.environ.get("KSEO_STAGE") != "benchmark":
        raise KSEOError("HTTP adapter 只接受 measured benchmark 阶段")
    manifest = read_json(Path(os.environ["KSEO_WORKLOAD_FILE"]))
    endpoint = os.environ["KSEO_BASE_URL"].rstrip("/") + "/chat/completions"
    api_key = os.environ.get("KSEO_API_KEY", "")
    timeout = float(os.environ.get("KSEO_HTTP_TIMEOUT", "600"))
    records = []
    for case in manifest["cases"]:
        def worker(request):
            try:
                return measure(request, case["id"], endpoint, api_key=api_key, timeout=timeout)
            except Exception as exc:
                # 只记录错误类别，避免把响应正文或 credentials 写入日志。
                return {"request_id": request["request_id"], "case_id": case["id"], "status": "failed",
                        "input_tokens": request["input_tokens"], "error_type": type(exc).__name__}
        with ThreadPoolExecutor(max_workers=case.get("concurrency", 1)) as pool:
            records.extend(pool.map(worker, case["requests"]))
    emit(requests=records)


if __name__ == "__main__":
    main()
