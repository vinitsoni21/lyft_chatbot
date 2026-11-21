import os
from dotenv import load_dotenv

load_dotenv()

# Key pool: key ids are key_1, key_2, ... in this order
LLM_API_KEYS = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]

LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"

DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT", "You are a helpful assistant. Keep answers concise."
)


def sqlite_path() -> str:
    """Turn sqlite:////data/app.db into /data/app.db (and sqlite:///./app.db into ./app.db)."""
    prefix = "sqlite:///"
    if DATABASE_URL.startswith(prefix):
        return DATABASE_URL[len(prefix):]
    return DATABASE_URL