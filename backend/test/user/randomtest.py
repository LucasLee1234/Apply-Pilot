import os
from pathlib import Path

from common.config import ENV
from dotenv import load_dotenv
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=ENV_FILE)

print(ENV_FILE)