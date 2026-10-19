import io
import json
import unittest
from unittest.mock import patch

from kseo.http_benchmark import measure
from kseo.util import KSEOError


class HTTPTests(unittest.TestCase):
    def request(self):
        return {"request_id": "r1", "input_tokens": 10, "payload": {"model": "test", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 4}}

    def stream(self, *, usage=True, cache=True):
        objects = [{"choices": [{"delta": {"role": "assistant"}}]},
                   {"choices": [{"delta": {"reasoning_content": "think"}}]},
                   {"choices": [{"delta": {"content": "answer"}}]}]
        if usage:
            value = {"prompt_tokens": 10, "completion_tokens": 4}
            if cache: value["prompt_tokens_details"] = {"cached_tokens": 0}
            objects.append({"choices": [], "usage": value})
        return io.BytesIO(("".join("data: " + json.dumps(o) + "\n\n" for o in objects) + "data: [DONE]\n\n").encode())

    def test_actual_usage_and_reasoning_stream(self):
        with patch("urllib.request.urlopen", return_value=self.stream()):
            result = measure(self.request(), "c1", "http://example.test/v1/chat/completions")
        self.assertEqual(result["output_tokens"], 4)
        self.assertEqual(result["input_tokens"], 10)
        self.assertGreaterEqual(result["total_ms"], result["ttft_ms"])

    def test_missing_usage_not_fabricated(self):
        with patch("urllib.request.urlopen", return_value=self.stream(usage=False)):
            with self.assertRaises(KSEOError): measure(self.request(), "c1", "http://example.test/v1/chat/completions")

    def test_missing_cache_evidence_not_assumed_zero(self):
        with patch("urllib.request.urlopen", return_value=self.stream(cache=False)):
            with self.assertRaises(KSEOError): measure(self.request(), "c1", "http://example.test/v1/chat/completions")
