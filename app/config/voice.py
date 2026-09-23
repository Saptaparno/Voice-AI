"""VAD / microphone-specific constants for the listener agent."""

from app.config import (
    MIC_DEVICE_INDEX,
    VAD_AGGRESSIVENESS,
    SAMPLE_RATE,
    SILENCE_END_MS,
    MAX_UTTERANCE_MS,
    PRE_SPEECH_MS,
    MIN_SPEECH_MS,
    LEADING_SILENCE_MS,
)

__all__ = [
    "MIC_DEVICE_INDEX",
    "VAD_AGGRESSIVENESS",
    "SAMPLE_RATE",
    "SILENCE_END_MS",
    "MAX_UTTERANCE_MS",
    "PRE_SPEECH_MS",
    "MIN_SPEECH_MS",
    "LEADING_SILENCE_MS",
]
