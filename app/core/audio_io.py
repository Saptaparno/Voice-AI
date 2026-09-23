"""Audio container utilities — pure stdlib."""

import io
import wave


def pcm_to_wav(pcm_bytes, *, sample_rate=16000, channels=1, sample_width=2):
    """Wrap raw 16-bit PCM bytes in a WAV container (in memory).

    Args:
        pcm_bytes: Raw PCM audio data.
        sample_rate: Samples per second (default 16000).
        channels: Number of channels (default 1, mono).
        sample_width: Bytes per sample (default 2 = 16-bit).

    Returns:
        bytes: Complete WAV file contents.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
