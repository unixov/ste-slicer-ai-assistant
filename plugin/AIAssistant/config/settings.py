import os


DEFAULT_BASE_URL = "https://api.timeweb.ai/v1"
DEFAULT_MODEL = "dashscope/qwen3.8-flash"

# Path to .env at the plugin root (one level up from config/)
# Works both in the repo (plugin/AIAssistant/) and after installation
# (…/plugins/AIAssistant/)
_ENV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", ".env",
)


def _load_env_file():
    """Read key=value pairs from .env if it exists; do not override existing env vars."""
    try:
        with open(_ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except (IOError, OSError):
        pass  # .env not present — that's fine


# Load once at import time
_load_env_file()


def get_base_url():
    return os.environ.get("STE_SLICER_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_model():
    return os.environ.get("STE_SLICER_AI_MODEL", DEFAULT_MODEL)


def get_api_key():
    """Read the key from env var or .env file; never hard-coded in source."""
    return os.environ.get("STE_SLICER_AI_API_KEY", "")
