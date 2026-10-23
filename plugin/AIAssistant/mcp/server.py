import json

from .protocol import McpProtocolError, make_error, make_result, parse_request


class McpServer(object):
    def __init__(self, registry, server_name="ste-slicer-ai-assistant", version="0.1.0"):
        self._registry = registry
        self._server_name = server_name
        self._version = version

    def list_tools(self):
        return self._registry.list_tools()

    def handle(self, payload):
        request_id = None
        try:
            request = parse_request(payload)
            request_id = request.get("id")
            method = request["method"]
            params = request.get("params") or {}

            if method == "initialize":
                return make_result(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": self._server_name,
                            "version": self._version,
                        },
                    },
                )

            if method == "tools/list":
                return make_result(request_id, {"tools": self._registry.list_tools()})

            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                confirm = bool(params.get("confirmed", False))
                result = self._registry.call(name, arguments, confirm=confirm)
                return make_result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False),
                            }
                        ]
                    },
                )

            if method == "notifications/initialized":
                return None

            return make_error(request_id, -32601, "Method not found: " + method)
        except McpProtocolError as error:
            return make_error(request_id, error.code, error.message)
        except KeyError as error:
            return make_error(request_id, -32602, str(error))
        except Exception as error:
            return make_error(request_id, -32000, str(error))
