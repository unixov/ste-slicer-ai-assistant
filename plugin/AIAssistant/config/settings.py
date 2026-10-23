import os


DEFAULT_BASE_URL = "https://api.timeweb.ai/v1"
DEFAULT_MODEL = "dashscope/qwen3.8-flash"


def get_base_url():
    return os.environ.get("STE_SLICER_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_model():
    return os.environ.get("STE_SLICER_AI_MODEL", DEFAULT_MODEL)


def get_api_key():
    """Read the key locally; never provide a secret as a source-code default."""
    return os.environ.get("STE_SLICER_AI_API_KEY", "")
