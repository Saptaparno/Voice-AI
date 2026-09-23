"""Sarvam Saaras v3 speech-to-text service."""

import io
import struct

from app.config import SARVAM_STT_URL, SARVAM_STT_MODEL, SARVAM_LANGUAGE_CODE
from app.config.sarvam import load_sarvam_credentials
from app.core.audio_io import pcm_to_wav
from app.core.http import post_with_retry
from app.models import Transcript


def transcribe(pcm_bytes: bytes, sample_rate: int = 16000) -> Transcript:
    """Transcribe 16-bit mono PCM audio via Sarvam Saaras v3.

    Args:
        pcm_bytes: Raw PCM audio captured from the mic (or a telephony stream).
        sample_rate: Sample rate of ``pcm_bytes`` in Hz.

    Returns:
        Transcript: always returned; ``text`` is empty on failure.
    """
    if not pcm_bytes:
        return Transcript(text="")

    wav_bytes = pcm_to_wav(pcm_bytes, sample_rate=sample_rate)

    # PCM diagnostics — print audio statistics
    n_samples = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes)
    abs_sum = sum(abs(s) for s in samples)
    max_val = max(samples) if samples else 0
    min_val = min(samples) if samples else 0
    rms = (abs_sum / n_samples) if n_samples else 0
    nonzero = sum(1 for s in samples if s != 0)
    print(f"[STT] PCM={len(pcm_bytes)} bytes ({n_samples} samples, {nonzero} non-zero) "
          f"→ WAV={len(wav_bytes)} bytes | "
          f"rms={rms:.1f} max={max_val} min={min_val}")
    print(f"[STT] WAV header: {wav_bytes[:64].hex()}")

    creds = load_sarvam_credentials()

    try:
        resp = post_with_retry(
            SARVAM_STT_URL,
            headers={**creds.subscription_headers},
            files={
                "file": ("utterance.wav", wav_bytes, "audio/wav"),
                "model": (None, SARVAM_STT_MODEL),
                "language_code": (None, SARVAM_LANGUAGE_CODE),
            },
            timeout=30,
        )
    except Exception as e:
        print(f"[STT] request failed: {e}")
        return Transcript(text="")

    data = resp.json()
    transcript = (data.get("transcript") or "").strip()
    print(f"[STT] result: {transcript!r}  lang={data.get('language_code')} "
          f"conf={data.get('confidence')}")
    return Transcript(
        text=transcript,
        language_code=data.get("language_code"),
        confidence=data.get("confidence"),
    )
