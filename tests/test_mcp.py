import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin", "AIAssistant"))

from mcp.registry import ToolRegistry
from mcp.server import McpServer


class McpTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(
            "read.value",
            "Read a value.",
            {"type": "object", "properties": {}},
            lambda arguments: {"value": 42},
        )
        self.registry.register(
            "write.value",
            "Write a value.",
            {"type": "object", "properties": {"value": {"type": "number"}}},
            lambda arguments: {"written": arguments["value"]},
            requires_confirmation=True,
        )
        self.server = McpServer(self.registry)

    def test_initialize(self):
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        self.assertEqual(response["result"]["serverInfo"]["name"], "ste-slicer-ai-assistant")

    def test_list_tools(self):
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        self.assertEqual(len(response["result"]["tools"]), 2)

    def test_read_tool(self):
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "read.value"},
            }
        )
        data = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(data["value"], 42)

    def test_write_requires_confirmation(self):
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "write.value", "arguments": {"value": 7}},
            }
        )
        data = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(data["requires_confirmation"])

    def test_invalid_method(self):
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": 5, "method": "unknown"}
        )
        self.assertEqual(response["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
