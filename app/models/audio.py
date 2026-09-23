"""Audio data shapes — Pydantic models."""

from pydantic import BaseModel, Field, computed_field


class Utterance(BaseModel):
    """Captured audio from a telephony stream.

    Attributes:
        pcm_bytes: Raw 16-bit PCM audio data.
        sample_rate: Samples per second (default 16000).
        channels: Number of channels (default 1, mono).
    """

    pcm_bytes: bytes
    sample_rate: int = 16000
    channels: int = 1

    @computed_field
    @property
    def duration_ms(self) -> int:
        """Approximate duration of the audio in milliseconds."""
        if self.channels == 0 or self.sample_rate == 0:
            return 0
        bytes_per_sample = 2  # 16-bit
        total_samples = len(self.pcm_bytes) // (self.channels * bytes_per_sample)
        return int(total_samples / self.sample_rate * 1000)
