"""Telephony voice controller — Plivo WebSocket audio streaming.

Flow:
  Plivo opens WebSocket → sends "start" event → sends "media" frames
  → we VAD-segment → STT → LLM → TTS → send "playAudio" frames
  → Plivo plays audio to caller.

Plivo WebSocket protocol (from their docs):
  Inbound (Plivo → us): {"event": "media", "media": {"payload": "<base64>"}}
  Outbound (us → Plivo): {"event": "playAudio", "media": {"contentType": "audio/x-l16",
                                "sampleRate": 16000, "payload": "<base64>"}}
"""

import asyncio
import base64
import json
import struct
import time
from typing import Any

from app.agents.reasoner import ConversationHistory, ask as reasoner_ask
from app.config.sarvam import load_sarvam_credentials
from app.core.http import post_with_retry
from app.core.text import strip_markdown
from app.models import CallContext, Utterance
from app.services.mongo_logging import mongo_logger

from app.config.voice import (
    MAX_UTTERANCE_MS,
    SAMPLE_RATE,
    SILENCE_END_MS,
    VAD_AGGRESSIVENESS,
)
import webrtcvad


# ---------------------------------------------------------------------------
# Plivo WebSocket event names
# ---------------------------------------------------------------------------

class PlivoEvent:
    START = "start"
    MEDIA = "media"
    STOP = "stop"
    DTMF = "dtmf"


# ---------------------------------------------------------------------------
# TTS → Plivo WebSocket
# ---------------------------------------------------------------------------

async def _stream_tts_to_ws(
    ws,
    text: str,
    content_type: str = "audio/x-l16",
    sample_rate: int = 16000,
    stream_id: str = "",
) -> bool:
    """Synthesize ``text`` via Sarvam Bulbul v3 and stream PCM to Plivo.

    Plivo expects WebSocket frames as JSON:
      {"event": "playAudio", "media": {"contentType": "...", "sampleRate": N,
                                         "streamId": "<id>", "payload": "<base64>"}}

    Args:
        ws: FastAPI WebSocket object.
        text: Text to speak.
        content_type: Must match the Stream XML contentType (default audio/x-l16).
        sample_rate: Must match the Stream XML sample rate (default 16000).
        stream_id: Plivo's streamId from the 'start' event (required for audio to play).

    Returns:
        True if streaming completed without error.
    """
    clean = strip_markdown(text)
    if not clean:
        return True

    print(f"\n[TTS] {clean}")

    if len(clean) > 2500:
        clean = clean[: 2497] + "..."

    from app.config import SARVAM_TTS_MODEL, SARVAM_TTS_URL, SARVAM_LANGUAGE_CODE

    payload = {
        "text": clean,
        "model": SARVAM_TTS_MODEL,
        "language_code": SARVAM_LANGUAGE_CODE,
        "speaker": "shubh",
        "output_audio_codec": "linear16",
        "speech_sample_rate": sample_rate,
        "pace": 1.0,
        "enable_preprocessing": True,
    }

    try:
        loop = asyncio.get_running_loop()
        creds = await loop.run_in_executor(None, load_sarvam_credentials)
        resp = await loop.run_in_executor(
            None,
            lambda: post_with_retry(
                SARVAM_TTS_URL,
                headers={
                    **creds.subscription_headers,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            ),
        )
    except Exception as e:
        print(f"[TTS] request failed: {e}")
        return False

    audios = resp.json().get("audios") or []
    if not audios:
        print(f"[TTS] empty audio list: {resp.text[:200]}")
        return False

    audio_bytes = base64.b64decode(audios[0])

    # If it's a WAV, strip the header. With output_audio_codec="linear16" it's raw PCM.
    pcm = _wav_to_pcm(audio_bytes)
    if not pcm:
        print(f"[TTS] ERROR: no PCM data extracted ({len(audio_bytes)} bytes received)")
        print(f"[TTS] audio hex (first 64 bytes): {audio_bytes[:64].hex()}")
        return False

    # Resample if TTS output rate differs from Plivo stream rate.
    if sample_rate != SAMPLE_RATE:
        pcm = _resample(pcm, sample_rate, SAMPLE_RATE)

    # Stream in 20 ms chunks (sample_rate × 2 bytes × 20ms).
    chunk_size = sample_rate * 2 * 20 // 1000
    duration_s = len(pcm) / (sample_rate * 2)
    print(f"[TTS] streaming {len(pcm)} bytes PCM at {sample_rate}Hz "
          f"→ {duration_s:.2f}s, chunks={chunk_size}B, streamId={stream_id[:8]}...")
    try:
        start_time = asyncio.get_event_loop().time()
        for i in range(0, len(pcm), chunk_size):
            controller = getattr(ws, "_voice_ai_controller", None)
            if controller is not None and controller._barge_in:
                print("[TTS] interrupted — caller started speaking")
                return False
            chunk = pcm[i : i + chunk_size]
            frame = json.dumps({
                "event": "playAudio",
                "media": {
                    "contentType": content_type,
                    "sampleRate": sample_rate,
                    "streamId": stream_id,
                    "payload": base64.b64encode(chunk).decode(),
                },
            })
            await ws.send_text(frame)

            # Pace chunks slightly ahead of real-time to avoid overflowing Plivo's buffer.
            elapsed = asyncio.get_event_loop().time() - start_time
            target = (i + len(chunk)) / (sample_rate * 2)
            if elapsed < target:
                await asyncio.sleep(target - elapsed)

        print(f"[TTS] done — sent {len(pcm) // chunk_size} chunks")
    except Exception as e:
        print(f"[TTS] WebSocket send error: {e}")
        return False

    return True


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    """Strip WAV header and return raw PCM. Handles variable-size headers."""
    if wav_bytes[:4] != b"RIFF":
        return wav_bytes  # assume raw PCM

    data_offset = 12
    while data_offset + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[data_offset : data_offset + 4]
        chunk_size = int.from_bytes(
            wav_bytes[data_offset + 4 : data_offset + 8], "little"
        )
        if chunk_id == b"data":
            return wav_bytes[data_offset + 8 : data_offset + 8 + chunk_size]
        data_offset += 8 + chunk_size

    return wav_bytes[44:]  # fallback


def _resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Simple linear interpolation resample. Only handles integer ratio downsampling."""
    if from_rate == to_rate:
        return pcm
    ratio = from_rate // to_rate
    assert from_rate % to_rate == 0, "only integer-ratio resampling supported"
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    resampled = [samples[i] for i in range(0, len(samples), ratio)]
    return struct.pack(f"<{len(resampled)}h", *resampled)


# ---------------------------------------------------------------------------
# Telephony controller
# ---------------------------------------------------------------------------

class TelephonyController:
    """Runs a voice assistant session inside a Plivo call.

    Orchestrates listen → think → speak over the Plivo WebSocket.
    """

    def __init__(
        self,
        call_uuid: str = "unknown",
        from_number: str = "",
        to_number: str = "",
    ):
        self.call_uuid = call_uuid
        self.from_number = from_number
        self.to_number = to_number
        self._stopped = False
        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        # Audio format negotiated by Plivo's "start" event.
        self._content_type = "audio/x-l16"
        self._sample_rate = 16000
        self._stream_id = ""  # set by _on_start
        # PCM ring buffer — filled by _on_media / pump_messages,
        # drained by _read_utterance.
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        # Tracks whether we are mid-utterance (for VAD).
        self._triggered = False
        self._voiced = bytearray()
        self._silence_ms = 0
        self._pre_roll = bytearray()
        self._frame_count = 0
        self._tts_active = False
        self._barge_in = False
        self._speech_frames_during_tts = 0
        self._started_at = time.time()
        self._turns = 0
        self._metrics = {"stt_latency_ms": [], "llm_latency_ms": [],
                         "tts_latency_ms": [], "audio_duration_ms": [],
                         "tts_characters": 0, "estimated_cost_inr": 0.0, "turn_count": 0}
        self._logging_finished = False

    def finish_logging(self, error: str | None = None) -> None:
        """Persist final call metrics; safe to call more than once."""
        if self._logging_finished:
            return
        self._logging_finished = True
        self._metrics["duration_ms"] = round((time.time() - self._started_at) * 1000, 2)
        self._metrics["estimated_cost_inr"] = round(self._metrics["estimated_cost_inr"], 8)
        stt_seconds = sum(self._metrics["audio_duration_ms"]) / 1000
        tts_cost = self._metrics["tts_characters"] * 30 / 10000
        stt_cost = stt_seconds * 30 / 3600
        llm_cost = self._metrics["estimated_cost_inr"]
        self._metrics["cost_breakup"] = {
            "saaras_stt": {"audio_seconds": round(stt_seconds, 3), "cost_inr": round(stt_cost, 8)},
            "bulbul_tts": {"characters": self._metrics["tts_characters"], "cost_inr": round(tts_cost, 8)},
            "sarvam_105b": {"cost_inr": llm_cost},
            "telephony_plivo": {"cost_inr": None, "source": "Plivo hangup webhook"},
            "total_cost_inr": round(stt_cost + tts_cost + llm_cost, 8),
        }
        mongo_logger.finish_call(self.call_uuid, self._metrics, error)

    # ------------------------------------------------------------------
    # WebSocket event handlers
    # ------------------------------------------------------------------

    def on_ws_event(self, event: dict[str, Any]) -> None:
        """Route a Plivo WebSocket JSON event to the appropriate handler."""
        etype = event.get("event", "")
        if etype == PlivoEvent.START:
            self._on_start(event)
        elif etype == PlivoEvent.MEDIA:
            self._on_media(event)
        elif etype == PlivoEvent.STOP:
            print(f"[WS] Plivo sent 'stop' event — stream ended")
            self._stopped = True
            try:
                self._audio_queue.put_nowait(None)  # sentinel
            except Exception:
                pass
        elif etype == PlivoEvent.DTMF:
            digit = event.get("dtmf", {}).get("digit", "")
            print(f"[WS] DTMF digit: {digit}")

    def _on_start(self, event: dict[str, Any]) -> None:
        """Handle Plivo's 'start' event — extract audio format and stream ID."""
        print(f"[WS start raw] {json.dumps(event)}")
        start = event.get("start", {})
        media_format = start.get("mediaFormat", {})
        self._content_type = media_format.get("encoding", "audio/x-l16")
        self._sample_rate = int(media_format.get("sampleRate", 16000))
        self._stream_id = start.get("streamId", "")
        self.call_uuid = start.get("callId", self.call_uuid)
        print(f"[WS] Stream started — format={self._content_type} "
              f"rate={self._sample_rate}Hz streamId={self._stream_id} "
              f"call_uuid={self.call_uuid}")

    def _on_media(self, event: dict[str, Any]) -> None:
        """Handle Plivo's 'media' event — queue PCM for VAD processing."""
        if self._stopped:
            return
        media = event.get("media", {})
        payload_b64 = media.get("payload", "")

        if not payload_b64:
            return

        pcm = base64.b64decode(payload_b64)

        # μ-law decode if needed (Plivo sends mu-law by default).
        if self._content_type == "audio/x-mulaw":
            pcm = _mulaw_to_linear(pcm)

        if self._tts_active:
            if self._is_speech(pcm):
                self._speech_frames_during_tts += 1
                if self._speech_frames_during_tts >= 3:
                    self._barge_in = True
            else:
                self._speech_frames_during_tts = 0

        # Periodic signal report on the RAW inbound audio, before amplify/VAD:
        # peak==0 across the call means Plivo is streaming us pure silence.
        self._frame_count += 1
        if self._frame_count <= 3 or self._frame_count % 50 == 0:
            peak = max(
                (abs(s) for s in struct.unpack(f"<{len(pcm) // 2}h", pcm)), default=0
            )
            print(f"[WS media] #{self._frame_count} track={media.get('track')} "
                  f"bytes={len(pcm)} peak={peak}")

        # Ring-buffer semantics: the queue fills while we are mid-TTS (nothing
        # drains it then), so drop the oldest frame instead of letting
        # QueueFull escape into the WebSocket reader task and kill it.
        try:
            self._audio_queue.put_nowait(pcm)
        except asyncio.QueueFull:
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._audio_queue.put_nowait(pcm)

    def stop(self) -> None:
        self._stopped = True
        try:
            self._audio_queue.put_nowait(None)  # sentinel to unblock _read_utterance
        except Exception:
            pass

    def drain_queue(self) -> bytes:
        """Drain all pending audio from the queue into a single buffer.

        Call this after cancelling a _read_utterance task to recover any
        audio that arrived during that task.
        """
        collected = bytearray()
        while True:
            try:
                frame = self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if frame is None:
                break
            collected.extend(frame)
        return bytes(collected)

    # ------------------------------------------------------------------
    # Main async loop
    # ------------------------------------------------------------------

    async def run_async(self, ws) -> None:
        """Run the voice assistant loop on the Plivo WebSocket.

        Architecture — TTS and caller-listening run CONCURRENTLY:
        1. While TTS streams audio, caller audio is buffered.
        2. After TTS finishes, we immediately process the caller's utterance
           (if they spoke during or before the TTS).
        3. Subsequent turns run TTS and STT concurrently so the caller can
           barge in at any time.
        """
        # Wait for Plivo's 'start' event — it carries streamId and audio format.
        while not self._stream_id and not self._stopped:
            await asyncio.sleep(0.05)

        if self._stopped:
            return

        # The start event may replace the query-string fallback with Plivo's
        # actual call ID. Persist only after that ID is available.
        mongo_logger.start_call(self.call_uuid, self.from_number, self.to_number)

        # ------------------------------------------------------------------
        # Greeting — TTS only, then wait for AEC to settle before listening.
        # Running TTS and STT concurrently causes Plivo's AEC to suppress
        # the caller's voice (it sees the TTS audio in the mic).
        # ------------------------------------------------------------------
        print(f"[WS] streamId ready — greeting caller")
        await _stream_tts_to_ws(
            ws,
            "Hello! I am your voice assistant. How can I help you today?",
            content_type=self._content_type,
            sample_rate=self._sample_rate,
            stream_id=self._stream_id,
        )

        # Drain the greeting buffer (filled with AEC-cancelled silence).
        greeting_bytes = self.drain_queue()
        if greeting_bytes:
            print(f"[Telephony] drained {len(greeting_bytes)} bytes (AEC silence)")

        # Wait for speaker to stop and AEC to release before we start listening.
        await asyncio.sleep(0.3)

        if self._stopped:
            return

        history = ConversationHistory()
        ws._voice_ai_controller = self

        # ------------------------------------------------------------------
        # Main loop — sequential: listen → STT → LLM → TTS → drain AEC.
        # Running TTS and STT concurrently causes Plivo's AEC to suppress
        # the caller's voice. TTS must finish and AEC must settle before
        # we start listening for the next response.
        # ------------------------------------------------------------------
        while not self._stopped:
            print(f"[Telephony listening] call_uuid={self.call_uuid}")
            pcm = await self._read_utterance()

            if self._stopped or pcm is None:
                break

            if not pcm:
                continue

            # Normalize the whole utterance at once — doing it per 20ms frame
            # flattens the dynamics VAD relies on and makes it fire on noise.
            utt = Utterance(pcm_bytes=_amplify(pcm), sample_rate=self._sample_rate)
            loop = asyncio.get_running_loop()
            from app.services.sarvam_stt import transcribe
            stt_started = time.perf_counter()
            result = await loop.run_in_executor(
                None, lambda: transcribe(utt.pcm_bytes, sample_rate=utt.sample_rate)
            )
            stt_latency_ms = round((time.perf_counter() - stt_started) * 1000, 2)
            self._metrics["stt_latency_ms"].append(stt_latency_ms)
            self._metrics["audio_duration_ms"].append(utt.duration_ms)
            user_text = result.text.strip()

            if not user_text:
                continue

            print(f"[Telephony] {self.from_number} said: {user_text}")

            if history.is_exit(user_text):
                print("[Telephony] exit phrase detected")
                break

            # LLM
            llm_started = time.perf_counter()
            chat_result = reasoner_ask(user_text, history)
            llm_latency_ms = round((time.perf_counter() - llm_started) * 1000, 2)
            reply = chat_result.text
            self._metrics["llm_latency_ms"].append(llm_latency_ms)
            self._metrics["estimated_cost_inr"] += (
                chat_result.prompt_tokens * 29.28 / 1_000_000
                + chat_result.completion_tokens * 73.20 / 1_000_000
            )
            self._turns += 1
            self._metrics["turn_count"] = self._turns
            mongo_logger.add_turn(self.call_uuid, {
                "turn": self._turns, "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                "user_text": user_text, "assistant_text": reply,
                "history": history.to_list(), "stt": {"latency_ms": stt_latency_ms,
                "language_code": result.language_code, "confidence": result.confidence,
                "audio_duration_ms": utt.duration_ms},
                "llm": {"latency_ms": llm_latency_ms, "prompt_tokens": chat_result.prompt_tokens,
                "completion_tokens": chat_result.completion_tokens, "total_tokens": chat_result.total_tokens,
                "estimated_cost_inr": chat_result.prompt_tokens * 29.28 / 1_000_000 + chat_result.completion_tokens * 73.20 / 1_000_000}
            })
            print(f"[Telephony] AI: {reply}")

            # TTS — wait for it to finish completely.
            tts_started = time.perf_counter()
            self._tts_active = True
            self._barge_in = False
            self._speech_frames_during_tts = 0
            await _stream_tts_to_ws(
                ws,
                reply,
                content_type=self._content_type,
                sample_rate=self._sample_rate,
                stream_id=self._stream_id,
            )
            self._tts_active = False
            self._metrics["tts_latency_ms"].append(round((time.perf_counter() - tts_started) * 1000, 2))
            self._metrics["tts_characters"] += len(strip_markdown(reply)[:2500])

            # Drain AEC garbage and wait for it to release before listening again.
            self.drain_queue()
            await asyncio.sleep(0.3)

        if not self._stopped:
            try:
                self._tts_active = True
                self._barge_in = False
                self._speech_frames_during_tts = 0
                await _stream_tts_to_ws(
                    ws,
                    "Goodbye! Have a nice day.",
                    content_type=self._content_type,
                    sample_rate=self._sample_rate,
                    stream_id=self._stream_id,
                )
                self._tts_active = False
            except Exception:
                pass
        self.finish_logging()

    # ------------------------------------------------------------------
    # VAD-gated utterance reading from the audio queue
    # ------------------------------------------------------------------

    async def _read_utterance(self) -> bytes | None:
        """Block until a complete utterance (speech → silence) is captured."""
        pre_roll_frames = 200 // 20  # 200 ms pre-roll
        triggered = False
        voiced = bytearray()
        silence_ms = 0
        total_ms = 0
        pre_roll = bytearray()

        while not self._stopped:
            try:
                frame = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue

            if frame is None:  # sentinel — stream ended
                return bytes(voiced) if voiced else None

            total_ms += 20

            if not triggered:
                pre_roll.extend(frame)
                if len(pre_roll) > pre_roll_frames * len(frame):
                    pre_roll = pre_roll[-pre_roll_frames * len(frame):]

                if self._is_speech(frame):
                    triggered = True
                    voiced.extend(pre_roll)
                    voiced.extend(frame)
                    silence_ms = 0
                elif total_ms > MAX_UTTERANCE_MS:
                    return None
                continue

            voiced.extend(frame)

            if self._is_speech(frame):
                silence_ms = 0
            else:
                silence_ms += 20
                if silence_ms >= SILENCE_END_MS:
                    return bytes(voiced)

            if total_ms > MAX_UTTERANCE_MS:
                return bytes(voiced)

        return bytes(voiced) if voiced else None

    def _is_speech(self, frame: bytes) -> bool:
        try:
            return self._vad.is_speech(frame, self._sample_rate)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Audio format utilities
# ---------------------------------------------------------------------------

def _amplify(pcm: bytes, *, target_rms: float = 2000.0) -> bytes:
    """Amplify PCM audio to a target RMS level.

    If the audio is too quiet (RMS < target), multiply all samples by a
    gain factor. Clamp to prevent clipping.
    """
    if not pcm:
        return pcm

    n = len(pcm) // 2
    samples = struct.unpack(f"<{n}h", pcm)

    rms = (sum(s * s for s in samples) / n) ** 0.5
    if rms < 1.0:  # near-silence, skip amplification
        return pcm

    gain = min(target_rms / rms, 20.0)  # cap gain at 20x to avoid clipping
    if gain < 1.01:  # already loud enough
        return pcm

    amplified = [int(max(-32768, min(32767, s * gain))) for s in samples]
    return struct.pack(f"<{n}h", *amplified)


def _mulaw_to_linear(mulaw: bytes) -> bytes:
    """Convert μ-law PCM (8-bit) to 16-bit linear PCM."""
    import array
    import audioop

    try:
        return audioop.ulaw2lin(mulaw, 2)
    except audioop.error:
        # audioop fallback: manual μ-law decode
        out = []
        for byte in mulaw:
            # μ-law → linear (standard μ-law table)
            UL_LAW = [
                -32124, -31100, -30108, -29126, -28156, -27196, -26252, -25316,
                -24396, -23492, -22604, -21724, -20856, -20004, -19164, -18332,
                -17512, -16708, -15912, -15124, -14348, -13584, -12832, -12088,
                -11356, -10636, -9924, -9220, -8528, -7844, -7172, -6508,
                -5852, -5204, -4568, -3940, -3320, -2712, -2116, -1524,
                -940, -364, 364, 940, 1524, 2116, 2712, 3320,
                3940, 4568, 5204, 5852, 6508, 7172, 7844, 8528,
                9220, 9924, 10636, 11356, 12088, 12832, 13584, 14348,
                15124, 15912, 16708, 17512, 18332, 19164, 20004, 20856,
                21724, 22604, 23492, 24396, 25316, 26252, 27196, 28156,
                29126, 30108, 31100, 32124, 32767,
            ]
            linear = UL_LAW[byte] if byte < 128 else -UL_LAW[byte - 128]
            out.extend(struct.pack("<h", linear))
        return bytes(out)
