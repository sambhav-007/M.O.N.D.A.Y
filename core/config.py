"""
M.O.N.D.A.Y. — System Configuration & Environment Settings
===========================================================
Central configuration for directories, keys, security thresholds, and settings.
"""

from __future__ import annotations

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
STAGING_DIR = DATA_DIR / "staging"
MEMORIES_DB_PATH = DATA_DIR / "memory.db"
# The audit log is append-only JSON Lines: one record per line, never rewritten.
# It was a single JSON array, which `log_action` had to read, extend and write
# back on *every* action — O(file) per call against a file that only grows. By
# 2026-08-10 it held 19,837 entries / 6.5 MB, and the cost was showing up as a
# general slowdown in everything the assistant did.
ACTION_LOG_PATH = DATA_DIR / "action_history.jsonl"

# The old array-format log. Still read so history predating the change is not
# lost; never written to again.
LEGACY_ACTION_LOG_PATH = DATA_DIR / "action_history.json"

# Create directories if they don't exist
for d in [DATA_DIR, MODELS_DIR, LOGS_DIR, STAGING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# API Keys (optional for enhanced LLM reasoning, fallback to rule/ML engine if missing)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Security Thresholds
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
AUTO_EXECUTE_TIER_1 = True

# Server Settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Default country code for phone numbers typed without one. WhatsApp always
# needs a country code, and requiring the user to type +91 every time is friction
# they will not tolerate. Override with DEFAULT_COUNTRY_CODE in .env.
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
