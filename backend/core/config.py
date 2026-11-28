import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

WORKSPACE_ROOT = Path(
    os.getenv("ANGADGPT_WORKSPACE_ROOT", str(BASE_DIR))
).resolve()
MEMORY_DIR = BASE_DIR / "memory"
USER_DATA_DIR = Path(os.getenv("ANGADGPT_USER_DATA_DIR", str(MEMORY_DIR / "users"))).resolve()
SCRIPTS_DIR = BASE_DIR / "scripts"

MEMORY_DB_PATH = os.getenv("ANGADGPT_MEMORY_DB", str(MEMORY_DIR / "memory.sqlite3"))
CALENDAR_ICS_PATH = os.getenv("ANGADGPT_CALENDAR_ICS", str(MEMORY_DIR / "calendar.ics"))
CALENDAR_PROVIDER = os.getenv("ANGADGPT_CALENDAR_PROVIDER", "local")
GOOGLE_CALENDAR_ID = os.getenv("ANGADGPT_GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "ANGADGPT_GOOGLE_CREDENTIALS_PATH", str(MEMORY_DIR / "credentials.json")
)
GOOGLE_TOKEN_PATH = os.getenv(
    "ANGADGPT_GOOGLE_TOKEN_PATH", str(MEMORY_DIR / "token.json")
)

TINYLLM_MODEL_PATH = os.getenv("TINYLLM_MODEL_PATH", "")
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "")
LLM_PROVIDER = os.getenv("ANGADGPT_LLM_PROVIDER", "lmstudio").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
# gpt-oss is text-only; turns that carry an image need Groq's multimodal model.
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
GROQ_BASE_URL = "https://api.groq.com/openai"
LLM_TIMEOUT_SECONDS = float(os.getenv("ANGADGPT_LLM_TIMEOUT_SECONDS", "120"))

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ANGADGPT_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

AUTH_TOKEN = os.getenv("ANGADGPT_AUTH_TOKEN", "")
AUTH_MODE = os.getenv("ANGADGPT_AUTH_MODE", "clerk").strip().lower()

CLERK_ISSUER_URL = os.getenv("CLERK_ISSUER_URL", "").rstrip("/")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "").rstrip("/")
CLERK_AUDIENCE = os.getenv("CLERK_AUDIENCE", "")

SCHEDULER_TIMEZONE = os.getenv("ANGADGPT_TIMEZONE", "America/Detroit")

MAX_MEMORY_MESSAGES = int(os.getenv("ANGADGPT_MAX_MEMORY_MESSAGES", "50"))
SUMMARY_TARGET_MESSAGES = int(os.getenv("ANGADGPT_SUMMARY_TARGET_MESSAGES", "25"))
