import json

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen

from .settings import get_api_key, get_base_url, get_model


class LlmError(Exception):
    pass


def complete(messages, tools=None, timeout=60):
    api_key = get_api_key()
    if not api_key:
        raise LlmError("API-ключ не задан. Установите STE_SLICER_AI_API_KEY в окружении STE Slicer.")

    payload = {
        "model": get_model(),
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        get_base_url() + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )

    try:
        response = urlopen(request, timeout=timeout)
        raw = response.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as error:
        raise LlmError("Ошибка запроса к LLM: " + str(error))

    try:
        message = data["choices"][0]["message"]
        return message.get("content") or "", message.get("tool_calls") or []
    except (KeyError, IndexError, TypeError):
        raise LlmError("LLM вернула ответ неизвестного формата.")
