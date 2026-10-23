import json


class McpProtocolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def make_result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def parse_request(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            raise McpProtocolError(-32700, "Invalid JSON")

    if not isinstance(payload, dict):
        raise McpProtocolError(-32600, "Request must be an object")
    if payload.get("jsonrpc") != "2.0":
        raise McpProtocolError(-32600, "jsonrpc must be '2.0'")
    if "method" not in payload:
        raise McpProtocolError(-32600, "method is required")
    return payload
