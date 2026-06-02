"""
Configuration for the Multi-Agent Paper Analysis System.
Set your LLM API key via environment variable or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# LLM configuration - defaults to DeepSeek (OpenAI-compatible)
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# Retry and iteration settings
MAX_REVIEW_ROUNDS = int(os.getenv("MAX_REVIEW_ROUNDS", "2"))
MIN_REVIEW_SCORE = float(os.getenv("MIN_REVIEW_SCORE", "7.0"))

# Paths
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Search settings
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "12"))

# Report settings
OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "markdown")  # markdown or pdf



def validate_config():
    """Validate that required configuration is set."""
    issues = []
    if not LLM_API_KEY:
        issues.append(
            "LLM API Key is not set. "
            "Please set DEEPSEEK_API_KEY or OPENAI_API_KEY environment variable, "
            "or create a .env file in the project directory.\n"
            "Example: DEEPSEEK_API_KEY=sk-xxxx\n"
            "Get a key at: https://platform.deepseek.com"
        )
    return issues
