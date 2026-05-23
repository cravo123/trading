import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / "../../.env"


load_dotenv(_ENV_PATH, override=False)


class AuthenConfig:
    api_key = os.getenv("SCHWAB_API_KEY", "")
    app_secret = os.getenv("SCHWAB_APP_SECRET", "")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "")
