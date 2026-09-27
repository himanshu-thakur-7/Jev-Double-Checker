"""Settings loaded from the environment (and .env if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_API_BASE = os.getenv("TYPESAFE_API_BASE", "https://api.typesafe.ai")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-1.13.0")
# TypeSafe rate card: $0.042 per million input tokens, output free.
JEV_PRICE_IN_PER_M = float(os.getenv("JEV_PRICE_IN_PER_M", "0.042"))
JEV_PRICE_OUT_PER_M = float(os.getenv("JEV_PRICE_OUT_PER_M", "0"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
SECOND_OPINION_MODEL = os.getenv("SECOND_OPINION_MODEL", "gpt-6-sol")
