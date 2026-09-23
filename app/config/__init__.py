"""Central settings — loaded once from environment variables.

Import from here in all other modules; never call ``os.getenv`` elsewhere.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Locate .env relative to the repo root (one level above app/).
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


# ---------------------------------------------------------------------------
# Voice AI settings
# ---------------------------------------------------------------------------

VOICE_MODE = os.getenv("VOICE_MODE", "cli").strip().lower()  # cli | telephony

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful and friendly voice AI assistant. "
    "Keep responses short and conversational — 1 to 3 sentences. "
    "Use a warm, clear tone suitable for phone conversations."
).strip()

MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10").strip())

RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3").strip())
RETRY_BACKOFF_S = float(os.getenv("RETRY_BACKOFF_S", "2.0").strip())


# ---------------------------------------------------------------------------
# Sarvam (STT + TTS + LLM)
# ---------------------------------------------------------------------------

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_SUBSCRIPTION_KEY = os.getenv("SARVAM_SUBSCRIPTION_KEY", "").strip()

SARVAM_BASE_URL = "https://api.sarvam.ai"
SARVAM_STT_URL = f"{SARVAM_BASE_URL}/speech-to-text"
SARVAM_TTS_URL = f"{SARVAM_BASE_URL}/text-to-speech"

SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip()
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()
SARVAM_TTS_VOICE = os.getenv("SARVAM_TTS_VOICE", "shubh").strip()
SARVAM_LANGUAGE_CODE = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN").strip()

# OpenAI-compatible LLM endpoint (Sarvam's model)
OPENAI_API_KEY = SARVAM_API_KEY  # Same key, Sarvam is OpenAI-compatible.
OPENAI_BASE_URL = f"{SARVAM_BASE_URL}/v1"
SARVAM_CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b").strip()


# ---------------------------------------------------------------------------
# Microphone / VAD settings
# ---------------------------------------------------------------------------

MIC_DEVICE_INDEX = int(os.getenv("MIC_DEVICE_INDEX", "-1").strip())
VAD_AGGRESSIVENESS = int(os.getenv("VAD_AGGRESSIVENESS", "3").strip())
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000").strip())
SILENCE_END_MS = int(os.getenv("SILENCE_END_MS", "400").strip())
MAX_UTTERANCE_MS = int(os.getenv("MAX_UTTERANCE_MS", "60000").strip())
PRE_SPEECH_MS = int(os.getenv("PRE_SPEECH_MS", "200").strip())
MIN_SPEECH_MS = int(os.getenv("MIN_SPEECH_MS", "250").strip())

# How aggressively the mic stream flushes its internal ring buffer when
# silence is first detected.  Larger values give more context but increase
# latency.  Must be ≥ 0 and ≤ SILENCE_END_MS.
LEADING_SILENCE_MS = min(
    int(os.getenv("LEADING_SILENCE_MS", "200").strip()),
    SILENCE_END_MS,
)


# ---------------------------------------------------------------------------
# Plivo (telephony)
# ---------------------------------------------------------------------------

PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID", "").strip()
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN", "").strip()

# Incoming call webhook — Flask will bind to this when running telephony mode.
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0").strip()
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000").strip())



# Your Plivo DID that will make outbound calls.
PLIVO_CALLER_NUMBER = os.getenv("PLIVO_CALLER_NUMBER", "").strip()
