import json

try:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import HTTPError, Request, urlopen

from .settings import get_api_key, get_base_url, get_model


class LlmError(Exception):
    pass


_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _read_response(response):
    raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise LlmError("Ответ LLM слишком большой.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LlmError("Ответ LLM имеет неверную кодировку: " + str(error))


def _format_http_error(error):
    status = getattr(error, "code", "?")
    reason = getattr(error, "reason", "")
    details = ""
    try:
        raw = error.read(8192)
        details = raw.decode("utf-8", "replace").strip()
        parsed = json.loads(details)
        if isinstance(parsed, dict):
            details = str(parsed.get("error") or parsed.get("message") or details)
    except Exception:
        pass
    message = "HTTP %s" % status
    if reason:
        message += ": " + str(reason)
    if details:
        message += " — " + details[:1000]
    return message


def complete(messages, tools=None, timeout=60, force_text=False):
    api_key = get_api_key()
    if not api_key:
        raise LlmError("API-ключ не задан. Установите STE_SLICER_AI_API_KEY в окружении STE Slicer.")

    payload = {
        "model": get_model(),
        "messages": messages,
        "temperature": 0.2,
    }
    if tools and not force_text:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    elif tools and force_text:
        # Don't send tools at all — forces a plain text response
        pass
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
        raw = _read_response(response)
        data = json.loads(raw)
    except HTTPError as error:
        raise LlmError("Ошибка запроса к LLM: " + _format_http_error(error))
    except LlmError:
        raise
    except (ValueError, TypeError) as error:
        raise LlmError("LLM вернула некорректный JSON: " + str(error))
    except Exception as error:
        raise LlmError("Ошибка запроса к LLM: " + str(error))

    try:
        message = data["choices"][0]["message"]
        if not isinstance(message, dict):
            raise TypeError("message is not an object")
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []
        if content is not None and not isinstance(content, str):
            raise TypeError("content is not a string")
        if not isinstance(tool_calls, list):
            raise TypeError("tool_calls is not an array")
        return content or "", tool_calls
    except (KeyError, IndexError, TypeError):
        raise LlmError("LLM вернула ответ неизвестного формата.")
