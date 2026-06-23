"""
Configuration for the Academic Learning Path System.
Set API keys via environment variable or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM configuration ---
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# --- Search settings ---
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "15"))
DOWNLOAD_PAPER_COUNT = int(os.getenv("DOWNLOAD_PAPER_COUNT", "10"))

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PAPERS_DIR = os.path.join(BASE_DIR, "papers")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PAPERS_DIR, exist_ok=True)

# --- Email configuration (QQ Mail) ---
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.qq.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "465"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "1739362977@qq.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "1739362977@qq.com")


def validate_config():
    issues = []
    if not LLM_API_KEY:
        issues.append("LLM API Key not set. Set DEEPSEEK_API_KEY.")
    if not EMAIL_PASSWORD:
        issues.append("Email auth code not set. Set EMAIL_PASSWORD. For QQ Mail: Settings -> Account -> POP3/SMTP -> Generate authorization code.")
    return issues
