import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(
    os.getenv("ANGADGPT_WORKSPACE_ROOT", str(BASE_DIR))
).resolve()
MEMORY_DIR = BASE_DIR / "memory"
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

AUTH_TOKEN = os.getenv("ANGADGPT_AUTH_TOKEN", "")

SCHEDULER_TIMEZONE = os.getenv("ANGADGPT_TIMEZONE", "America/Detroit")

MAX_MEMORY_MESSAGES = int(os.getenv("ANGADGPT_MAX_MEMORY_MESSAGES", "50"))
SUMMARY_TARGET_MESSAGES = int(os.getenv("ANGADGPT_SUMMARY_TARGET_MESSAGES", "25"))
