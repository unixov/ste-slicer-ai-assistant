import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin", "AIAssistant"))

from config import llm_client


class _Response(object):
    def __init__(self, payload):
        self.payload = payload

    def read(self, size=-1):
        if size >= 0:
            return self.payload[:size]
        return self.payload


class LlmClientTests(unittest.TestCase):
    def setUp(self):
        self.old_urlopen = llm_client.urlopen
        self.old_key = os.environ.get("STE_SLICER_AI_API_KEY")
        os.environ["STE_SLICER_AI_API_KEY"] = "test-key"

    def tearDown(self):
        llm_client.urlopen = self.old_urlopen
        if self.old_key is None:
            os.environ.pop("STE_SLICER_AI_API_KEY", None)
        else:
            os.environ["STE_SLICER_AI_API_KEY"] = self.old_key

    def test_successful_completion_returns_content_and_tools(self):
        payload = {
            "choices": [{
                "message": {
                    "content": "Готово",
                    "tool_calls": [{"id": "call-1"}],
                },
            }],
        }
        llm_client.urlopen = lambda request, timeout: _Response(
            json.dumps(payload).encode("utf-8")
        )

        content, tool_calls = llm_client.complete(
            [{"role": "user", "content": "Привет"}],
            timeout=1,
        )

        self.assertEqual(content, "Готово")
        self.assertEqual(tool_calls, [{"id": "call-1"}])

    def test_http_error_includes_status_and_provider_message(self):
        def fail(request, timeout):
            raise llm_client.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"error": {"message": "invalid api key"}}'),
            )

        llm_client.urlopen = fail
        with self.assertRaises(llm_client.LlmError) as context:
            llm_client.complete([], timeout=1)

        self.assertIn("401", str(context.exception))
        self.assertIn("invalid api key", str(context.exception))

    def test_invalid_json_is_reported_as_llm_error(self):
        llm_client.urlopen = lambda request, timeout: _Response(b"not-json")

        with self.assertRaises(llm_client.LlmError) as context:
            llm_client.complete([], timeout=1)

        self.assertIn("некорректный JSON", str(context.exception))

    def test_oversized_response_is_rejected(self):
        payload = b"x" * (llm_client._MAX_RESPONSE_BYTES + 1)
        llm_client.urlopen = lambda request, timeout: _Response(payload)

        with self.assertRaises(llm_client.LlmError) as context:
            llm_client.complete([], timeout=1)

        self.assertIn("слишком большой", str(context.exception))

    def test_missing_api_key_is_rejected_before_network(self):
        os.environ.pop("STE_SLICER_AI_API_KEY", None)
        called = []
        llm_client.urlopen = lambda request, timeout: called.append(True)

        with self.assertRaises(llm_client.LlmError):
            llm_client.complete([], timeout=1)

        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
