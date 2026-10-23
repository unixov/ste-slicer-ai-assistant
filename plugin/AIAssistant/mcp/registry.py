class ToolRegistry(object):
    def __init__(self):
        self._tools = {}

    def register(self, name, description, schema, handler, requires_confirmation=False):
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": schema,
            "handler": handler,
            "requires_confirmation": requires_confirmation,
        }

    def list_tools(self):
        result = []
        for tool in self._tools.values():
            result.append(
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"],
                }
            )
        return result

    def call(self, name, arguments, confirm=False):
        if name not in self._tools:
            raise KeyError("Unknown tool: " + name)
        tool = self._tools[name]
        if tool["requires_confirmation"] and not confirm:
            return {
                "requires_confirmation": True,
                "tool": name,
                "message": "Инструмент требует подтверждения пользователя.",
            }
        return tool["handler"](arguments or {})
