import json
import os
import re
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize DeepSeek client (OpenAI SDK compatible)
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# DeepSeek chat model
MODEL = "deepseek-chat"

# ────────────────────────────── Debate Behavior ──────────────────────────────
# 0.0 = fully deferential (accept almost everything)
# 0.5 = balanced (defend when justified, revise when not)
# 1.0 = confident but respectful (explain a choice without arguing)
DEFENSE_LEVEL = 0.3

# Public repository URL; leave empty to skip fetching a repository snapshot.
GITHUB_REPO_URL = "https://github.com/Lawson-Dong/representation-alignment-/tree/representation-vector-geometric-dynamics"

# Initial CRITIC strictness, from gentle (0.0) to highly rigorous (1.0).
CRITIC_STRICTNESS = 0.4