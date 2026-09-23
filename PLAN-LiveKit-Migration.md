# Voice AI — Execution Plan: LiveKit Migration + M1 → M3

**Covers:** Infrastructure migration (Plivo → LiveKit as central hub) + voice agent milestones (M1 basic loop → M2 state + KB → M3 policy + reliability).
**Current status:** Plivo direct (working telephony); Sarvam STT/TTS/LLM (integrated); `app/agent.py` and `app/transports/` (do not exist yet).

---

## Table of Contents

1. [Current State Audit](#1-current-state-audit)
2. [Architecture: Current vs Target](#2-architecture-current-vs-target)
3. [What's Already Done](#3-whats-already-done)
4. [What Needs to be Built](#4-what-needs-to-be-built)
5. [M1 — Basic Voice Loop (Browser First)](#5-m1--basic-voice-loop-browser-first)
6. [M2 — Call State + Language + KB Tool](#6-m2--call-state--language--kb-tool)
7. [M3 — Policy Skeleton + Reliability](#7-m3--policy-skeleton--reliability)
8. [LiveKit Infrastructure Migration (Phase 1–3)](#8-livekit-infrastructure-migration-phase-13)
9. [Adding New Telephony Providers](#9-adding-new-telephony-providers)
10. [Final File Map](#10-final-file-map)
11. [Running Everything](#11-running-everything)

---

## 1. Current State Audit

### What exists today

| Layer | File(s) | Status |
|---|---|---|
| **FastAPI entry point** | `app/main.py` | ✅ Exists — Plivo routers mounted |
| **Config** | `app/config/__init__.py`, `settings.py`, `voice.py`, `plivo.py`, `sarvam.py` | ✅ Exists — all env vars in one place |
| **Sarvam STT** | `app/services/sarvam_stt.py` | ✅ Exists — works on raw PCM |
| **Sarvam LLM** | `app/services/sarvam_chat.py` | ✅ Exists — OpenAI-compatible |
| **Reasoner** | `app/agents/reasoner.py` | ✅ Exists — `ConversationHistory` + `ask()` |
| **Core utils** | `app/core/audio_io.py`, `http.py`, `text.py` | ✅ Exist — generic |
| **Models** | `app/models/` | ✅ Exist — Pydantic, generic + Plivo-specific |
| **Voice loop (Plivo)** | `app/controllers/telephony_controller.py` | ✅ Exists — Plivo WebSocket VAD/STT/LLM/TTS loop |
| **Inbound/Outbound** | `app/controllers/inbound.py`, `outbound.py` | ✅ Exist — Plivo XML + REST |
| **HTTP Routers** | `app/routers/plivo_webhook.py`, `telephony.py` | ✅ Exist — Plivo webhooks + WS |
| **Plivo client** | `app/services/plivo_client.py` | ✅ Exists |
| **Mongo logging** | `app/services/mongo_logging.py` | ✅ Exists (partial Plivo billing) |
| **Voice Agent** | `app/agent.py` | ❌ Does not exist |
| **LiveKit transport** | `app/transports/livekit.py` | ❌ Does not exist |
| **LiveKit token endpoint** | `app/routers/livekit_token.py` | ❌ Does not exist |
| **LiveKit SIP worker** | `app/routers/livekit_sip_worker.py` | ❌ Does not exist |
| **Session management** | `app/session.py` | ❌ Does not exist — needed for M2 |
| **Provider interfaces** | `app/providers/stt.py`, `tts.py`, `llm.py` | ❌ Do not exist — needed for M1 swap-ability |
| **KB tool client** | `app/services/kb_client.py` | ❌ Does not exist — needed for M2 |
| **Policy gate** | `app/policy.py` | ❌ Does not exist — needed for M3 |

---

## 2. Architecture: Current vs Target

### Current (Plivo direct — what exists today)

```
PSTN caller
    │
    ▼
Plivo Cloud
    │  ── HTTP POST /call/incoming ──► FastAPI ── XML <Stream>
    │  ── WebSocket /stream ───────────────► TelephonyController
    │  ── HTTP POST /call/hangup ─────────► FastAPI
    │                                             │
    │  audio_in (μ-law) ──► decode ──► VAD (webrtcvad)
    │                                   │
    │                                   ▼
    │                            Sarvam STT ──► text
    │                                   │
    │                                   ▼
    │                            Sarvam LLM ──► reply
    │                                   │
    │                                   ▼
    │                            Sarvam TTS ──► PCM
    │                                   │
    │                                   ▼
    │  audio_out (PCM) ──────────────────► WebSocket playAudio ──► Plivo
    ▼
PSTN caller hears TTS
```

**Problem:** Every new telephony provider (Exotel, Twilio, etc.) requires new WebSocket handlers, new webhook endpoints, new XML responses, and new audio protocol code.

### Target (LiveKit as central hub — what we build)

```
PSTN caller
    │
    ▼
Plivo / Exotel / Twilio / any SIP provider
    │  ← SIP INVITE
    ▼
LiveKit (self-hosted at livekit-infra.valura.co.in)
    │  ← SIP B2BUA — bridges PSTN ↔ WebRTC
    │  ← SIP participant joins LiveKit room
    ▼
LiveKit Room
    │
    ├── SIP participant (PSTN caller — audio via SIP)
    │
    └── Our agent (WebRTC participant — audio via LiveKit Core SDK)
              │
              ├── AudioStream (48kHz) ──► resample ──► 16kHz mono
              │                                   │
              │                                   ▼
              │                          inbound_audio()
              │                                   │
              │                                   ▼
              │                          VoiceAgent.run()
              │                                   │
              │                         ┌────────┴────────┐
              │                         │                 │
              │                         ▼                 ▼
              │                  VAD (webrtcvad)    STT (Sarvam)
              │                         │                 │
              │                         ▼                 ▼
              │                  _read_utterance()  LLM (Sarvam-105B)
              │                                          │
              │                                          ▼
              │                                  TTS (Sarvam Bulbul) ──► PCM
              │                                          │
              │                                          ▼
              │                                  AudioSource.capture_frame()
              │                                          │
              │                                          ▼
              │                                  LiveKit Room
              │                                          │
              │                                          ▼
              │                                  SIP participant hears TTS
```

**Why this works:** LiveKit handles all telephony complexity. Our agent is just a WebRTC participant in a LiveKit room. A SIP caller from any provider looks identical — it's a WebRTC audio track. Adding Exotel, Twilio, or any new provider = configure it in LiveKit's SIP console. **Zero code changes.**

---

## 3. What's Already Done

These files exist and are reusable across both Plivo (current) and LiveKit (target):

```
app/
├── config/
│   ├── __init__.py      ✅ All env vars — add LIVEKIT_* keys only
│   ├── settings.py      ✅ Re-exports voice/agent settings
│   ├── voice.py         ✅ VAD thresholds, sample rate, utterance limits
│   ├── sarvam.py        ✅ Sarvam credential builder
│   └── plivo.py         ✅ Plivo credential builder (delete in Phase 3)
├── core/
│   ├── audio_io.py      ✅ PCM ↔ WAV conversion (generic)
│   ├── http.py         ✅ Exponential-backoff HTTP (generic)
│   └── text.py         ✅ Markdown stripper for TTS (generic)
├── models/
│   ├── audio.py        ✅ Utterance (PCM + metadata)
│   ├── messages.py     ✅ Chat message (role + content)
│   ├── transcript.py   ✅ Transcript (text + language + confidence)
│   └── credentials.py  ✅ SarvamCredentials (keep), PlivoCredentials (delete)
├── agents/
│   └── reasoner.py     ✅ ConversationHistory + ask() — transport-agnostic
└── services/
    ├── sarvam_stt.py   ✅ transcribe(pcm) → Transcript
    └── sarvam_chat.py  ✅ ask_model(messages) → ChatResult
```

---

## 4. What Needs to be Built

### M1 additions (Voice Agent Core)

| File | Action | Description |
|---|---|---|
| `app/providers/stt.py` | **New** | `STTProvider` abstract interface + `SarvamSTTProvider` implementation |
| `app/providers/tts.py` | **New** | `TTSProvider` abstract interface + `SarvamTTSProvider` implementation |
| `app/providers/llm.py` | **New** | `LLMProvider` abstract interface + `SarvamLLMProvider` implementation |
| `app/agent.py` | **New** | `VoiceAgent` — VAD + STT + LLM + TTS pipeline, transport-agnostic |
| `app/transports/__init__.py` | **New** | Package init |
| `app/transports/livekit.py` | **New** | LiveKit Core SDK transport — AudioStream in, AudioSource out |
| `app/transports/browser.py` | **New** | Browser WS transport (for local dev without LiveKit SIP) |
| `app/routers/livekit_token.py` | **New** | `GET /livekit/token` — browser client JWT |
| `app/routers/livekit_sip_worker.py` | **New** | SIP inbound worker process |
| `app/main.py` | **Update** | Mount `livekit_router` alongside `plivo_router` (Phase 1 additive) |

### M2 additions (Session + Language + KB)

| File | Action | Description |
|---|---|---|
| `app/session.py` | **New** | `CallSession` — call state machine, language state, conversation history |
| `app/services/kb_client.py` | **New** | HTTP client to Voice Orchestrator for KB search (`search_support_kb`) |
| `app/agent.py` | **Update** | Add session state, language detection, KB tool call |
| `app/providers/stt.py` | **Update** | `LanguageResult` with detected language |

### M3 additions (Policy + Reliability)

| File | Action | Description |
|---|---|---|
| `app/policy.py` | **New** | `PolicyGate` — intercepts LLM tool calls, applies allow/deny rules |
| `app/resilience.py` | **New** | Circuit breaker (CLOSED/OPEN/HALF_OPEN), timeout wrappers |
| `app/agent.py` | **Update** | Add policy gate, circuit breakers, tool budget, idempotency keys |

### LiveKit Infrastructure (can start in parallel with M1)

| File | Action | Description |
|---|---|---|
| `.env.example` | **Update** | Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_SIP_ROOM` |
| `requirements.txt` | **Update** | Add `livekit>=1.0` |
| Plivo Console | **Config** | Update inbound trunk to route to LiveKit SIP endpoint |
| LiveKit Console | **Config** | Create inbound trunk + dispatch rule + outbound trunk |

### Phase 3 — Plivo Deprecation (after M1–M3 + LiveKit SIP confirmed)

| File | Action |
|---|---|
| `app/routers/plivo_webhook.py` | **Delete** |
| `app/routers/telephony.py` | **Delete** |
| `app/controllers/inbound.py` | **Delete** |
| `app/controllers/outbound.py` | **Delete** |
| `app/controllers/hangup.py` | **Delete** |
| `app/controllers/telephony_controller.py` | **Delete** |
| `app/services/plivo_client.py` | **Delete** |
| `app/config/plivo.py` | **Delete** |
| `app/services/mongo_logging.py` | **Update** — remove Plivo billing fields |

---

## 5. M1 — Basic Voice Loop (Browser First)

**Goal:** Prove realtime audio works. Browser client joins LiveKit room. Agent hears, thinks, speaks back. No SIP required for M1 testing.

**Exit criteria:**
- [ ] Worker joins LiveKit room and greets: "Hello, how can I help you?"
- [ ] User speaks → STT → LLM → TTS → user hears reply
- [ ] Barge-in / interruption does not crash the worker
- [ ] `STTProvider` and `TTSProvider` interfaces exist so Sarvam↔Deepgram can swap
- [ ] ≥ 20 internal test sessions documented (browser OK)
- [ ] README section: how to run locally

### M1 Build Order

#### Step 1 — Provider interfaces

Create `app/providers/stt.py`, `app/providers/tts.py`, `app/providers/llm.py`.

These abstract the service layer so we can swap Sarvam for Deepgram/STT or another LLM without touching the agent.

```python
# app/providers/stt.py
from abc import ABC, abstractmethod
from app.models.transcript import Transcript

class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> Transcript:
        ...

class SarvamSTTProvider(STTProvider):
    async def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> Transcript:
        from app.services.sarvam_stt import transcribe as _transcribe
        return _transcribe(pcm, sample_rate)
```

```python
# app/providers/tts.py
from abc import ABC, abstractmethod

class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Returns raw 16kHz mono PCM bytes.
        """
        ...
```

```python
# app/providers/llm.py
from abc import ABC, abstractmethod
from typing import Any

class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """Returns the assistant's reply text."""
        ...

    @abstractmethod
    async def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> tuple[str, list[dict]]:
        """
        Returns (text, tool_calls).
        tool_calls: [{'name': str, 'arguments': dict}]
        """
        ...
```

#### Step 2 — VoiceAgent (transport-agnostic)

Create `app/agent.py`. This is the core of the voice loop. It has **no knowledge of Plivo, LiveKit, or any telephony layer**. It receives raw PCM bytes, produces raw PCM bytes.

```python
"""Transport-agnostic voice AI — VAD, STT, LLM, TTS."""

import asyncio
import struct
import webrtcvad

from app.agents.reasoner import ConversationHistory
from app.config.voice import SILENCE_END_MS, MAX_UTTERANCE_MS, VAD_AGGRESSIVENESS, SAMPLE_RATE
from app.core.text import strip_markdown

def _amplify(pcm: bytes, *, target_rms: float = 2000.0) -> bytes:
    if not pcm:
        return pcm
    n = len(pcm) // 2
    samples = struct.unpack(f"<{n}h", pcm)
    rms = (sum(s * s for s in samples) / n) ** 0.5
    if rms < 1.0:
        return pcm
    gain = min(target_rms / rms, 20.0)
    if gain < 1.01:
        return pcm
    clamped = [int(max(-32768, min(32767, s * gain))) for s in samples]
    return struct.pack(f"<{n}h", *clamped)


class VoiceAgent:
    """
    Voice AI engine.

    No telephony knowledge. Receives PCM from an audio_source, speaks PCM
    through a tts_provider. Can be wired to any transport (LiveKit, browser WS,
    microphone, etc.).
    """

    def __init__(
        self,
        audio_source,          # async generator: yields raw 16kHz mono PCM bytes
        tts_provider,           # TTSProvider instance
        stt_provider=None,     # STTProvider instance (default: SarvamSTTProvider)
        llm_provider=None,      # LLMProvider instance (default: SarvamLLMProvider)
        system_prompt: str | None = None,
    ):
        self._audio_source = audio_source
        self._tts = tts_provider
        self._stt = stt_provider
        self._llm = llm_provider
        self._history = ConversationHistory(system_prompt=system_prompt)
        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self._running = False
        self._greeting_done = False

    async def run(self) -> None:
        """
        Run the full voice loop.

        1. Greet
        2. Capture utterance via VAD
        3. STT
        4. LLM
        5. TTS
        6. Publish to room
        7. Repeat until stopped
        """
        self._running = True
        await self.greet()

        while self._running:
            pcm = await self._read_utterance()
            if pcm is None:
                break

            result = self._stt.transcribe(_amplify(pcm))
            if not result.text.strip():
                continue

            print(f"[Agent] user: {result.text}")

            if self._history.is_exit(result.text):
                await self._speak("Goodbye! Have a great day.")
                break

            reply = self._history.ask(result.text)
            print(f"[Agent] AI: {reply}")

            await self._speak(reply)

    async def greet(self) -> None:
        if self._greeting_done:
            return
        await self._speak("Hello! How can I help you today?")
        self._greeting_done = True
        await asyncio.sleep(0.3)  # Let AEC settle

    async def _read_utterance(self) -> bytes | None:
        """Segment audio from audio_source into one utterance using VAD."""
        pre_roll_frames = 200 // 20
        triggered = False
        voiced = bytearray()
        silence_ms = 0
        pre_roll = bytearray()

        async for frame in self._audio_source():
            if not self._running:
                return bytes(voiced) if voiced else None

            if self._is_speech(frame):
                if not triggered:
                    triggered = True
                    voiced.extend(pre_roll)
                voiced.extend(frame)
                silence_ms = 0
            else:
                if triggered:
                    silence_ms += 20
                    if silence_ms >= SILENCE_END_MS:
                        return bytes(voiced)
                else:
                    pre_roll.extend(frame)
                    if len(pre_roll) > pre_roll_frames * len(frame):
                        pre_roll = pre_roll[-pre_roll_frames * len(frame):]

        return bytes(voiced) if voiced else None

    def _is_speech(self, frame: bytes) -> bool:
        try:
            return self._vad.is_speech(frame, SAMPLE_RATE)
        except Exception:
            return False

    async def _speak(self, text: str) -> None:
        """Synthesize TTS and publish PCM. Override in subclass or pass publish_fn."""
        tts_pcm = await self._tts.synthesize(strip_markdown(text))
        if tts_pcm:
            await self._publish_pcm(tts_pcm)

    async def _publish_pcm(self, pcm: bytes) -> None:
        """
        Override in a subclass (bound to a specific transport) or
        pass publish_fn at construction time.
        """
        raise NotImplementedError(
            "Override _publish_pcm or pass publish_fn to bind a transport"
        )

    def stop(self) -> None:
        self._running = False
```

#### Step 3 — TTS implementation

Create `app/providers/tts.py` with `SarvamTTSProvider`. Reuse the existing TTS logic from `telephony_controller.py` but return PCM instead of sending over WebSocket.

```python
# app/providers/tts.py
import asyncio
from abc import ABC, abstractmethod

class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Returns raw 16kHz mono PCM bytes."""
        ...

class SarvamTTSProvider(TTSProvider):
    """Sarvam Bulbul v3 TTS — returns raw PCM bytes."""

    def __init__(
        self,
        voice: str = "shubh",
        language_code: str = "en-IN",
        speed: float = 1.0,
    ):
        self.voice = voice
        self.language_code = language_code
        self.speed = speed

    async def synthesize(self, text: str) -> bytes:
        from app.services.sarvam_tts import synthesize_sarvam
        return await synthesize_sarvam(text, self.voice, self.language_code, self.speed)
```

Extract the existing TTS logic from `telephony_controller.py` into `app/services/sarvam_tts.py`:

```python
# app/services/sarvam_tts.py
"""Sarvam Bulbul v3 TTS — returns raw PCM bytes."""

import asyncio
import base64
import struct

from app.config import SARVAM_TTS_URL
from app.config.sarvam import load_sarvam_credentials
from app.core.http import post_with_retry

# Note: telephony_controller.py currently streams to WebSocket.
# This module captures PCM and returns it instead.

async def synthesize_sarvam(
    text: str,
    voice: str = "shubh",
    language_code: str = "en-IN",
    speed: float = 1.0,
) -> bytes:
    """
    Synthesize speech via Sarvam TTS. Returns raw 16kHz mono PCM bytes.
    """
    creds = load_sarvam_credentials()
    payload = {
        "inputs": [text],
        "target_language": language_code,
        "speaker": voice,
        "speaking_speed": str(speed),
        "model": "bulbul:v3",
    }
    headers = {
        "Authorization": f"Bearer {creds.api_key}",
        "api-subscription-key": creds.subscription_key,
    }

    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: post_with_retry(
            SARVAM_TTS_URL,
            headers=headers,
            json=payload,
            timeout=15,
        ),
    )
    data = resp.json()
    # Sarvam returns base64-encoded WAV or MP3. Handle both.
    audio_b64 = data.get("audios", [None])[0] or data.get("audio")
    if not audio_b64:
        return b""
    wav_data = base64.b64decode(audio_b64)
    return strip_wav_header(wav_data)


def strip_wav_header(wav_bytes: bytes) -> bytes:
    """Strip RIFF/WAV header, return raw 16kHz mono PCM."""
    import wave, io
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            if w.getnchannels() == 1 and w.getframerate() == 16000:
                return w.readframes(w.getnframes())
            # TODO: resample if needed
            return w.readframes(w.getnframes())
    except Exception:
        # Fallback: skip first 44 bytes (standard WAV header)
        return wav_bytes[44:] if len(wav_bytes) > 44 else wav_bytes
```

#### Step 4 — LiveKit transport

Create `app/transports/livekit.py`.

```python
"""LiveKit Core SDK transport — the only telephony transport going forward."""

import asyncio
import livekit.api as lk_api
import livekit.rtc as lk

from app.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from app.agent import VoiceAgent


def _generate_token(api_key: str, api_secret: str,
                    room: str, identity: str) -> str:
    token = lk_api.AccessToken(api_key, api_secret)
    token.with_identity(identity)
    token.with_grants(lk_api.VideoGrants(
        room_join=True, room=room,
        can_publish=True, can_subscribe=True))
    return token.to_jwt()


class LiveKitTransport:
    """
    Manages a LiveKit room session.

    Audio path:
      Remote participant mic → AudioStream → audio_source() → VoiceAgent
      VoiceAgent → publish_pcm() → AudioSource.capture_frame() → Room → All participants
    """

    def __init__(self, room_name: str, agent_identity: str = "voice-agent"):
        self.room_name = room_name
        self.agent_identity = agent_identity
        self._room: lk.Room | None = None
        self._audio_source: lk.AudioSource | None = None
        self._audio_track: lk.LocalAudioTrack | None = None
        self._remote_streams: list[lk.AudioStream] = []
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)

    async def connect(self) -> None:
        token = _generate_token(LIVEKIT_API_KEY, LIVEKIT_API_SECRET,
                               self.room_name, self.agent_identity)
        self._room = lk.Room()

        @self._room.on("track_subscribed")
        def on_track(track, _publication, _participant):
            if track.kind == lk.TrackKind.KIND_AUDIO:
                stream = lk.AudioStream(track, sample_rate=16000, num_channels=1)
                self._remote_streams.append(stream)
                asyncio.create_task(self._pump_stream(stream))

        await self._room.connect(LIVEKIT_URL, token)
        await self._publish_silence()

    async def _pump_stream(self, stream: lk.AudioStream) -> None:
        async for frame in stream:
            pcm = bytes(frame.data)
            try:
                self._audio_queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass

    async def _publish_silence(self) -> None:
        self._audio_source = lk.AudioSource(16000, 1)
        self._audio_track = lk.LocalAudioTrack.create_audio_track(
            "agent-tts", self._audio_source
        )
        await self._room.local_participant.publish_track(self._audio_track)
        silence = bytes(640)
        for _ in range(50):
            frame = lk.AudioFrame(
                data=silence, samples_per_channel=320,
                num_channels=1, sample_rate=16000,
            )
            await self._audio_source.capture_frame(frame)

    async def audio_source(self):
        """Async generator — yields raw 16kHz mono PCM from remote participants."""
        while True:
            try:
                pcm = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=5.0
                )
                yield pcm
            except asyncio.TimeoutError:
                continue

    async def publish_pcm(self, pcm: bytes) -> None:
        """Publish PCM to the room. Heard by all participants."""
        if self._audio_source is None:
            self._audio_source = lk.AudioSource(16000, 1)
            self._audio_track = lk.LocalAudioTrack.create_audio_track(
                "agent-tts", self._audio_source
            )
            await self._room.local_participant.publish_track(self._audio_track)

        chunk_size = 640
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i:i + chunk_size]
            frame = lk.AudioFrame(
                data=bytes(chunk), samples_per_channel=320,
                num_channels=1, sample_rate=16000,
            )
            await self._audio_source.capture_frame(frame)

    async def run_agent(self, agent: VoiceAgent) -> None:
        """Bind agent to this transport and run."""
        # Bind _publish_pcm to this transport
        original_publish = agent._publish_pcm

        async def bound_publish(pcm: bytes) -> None:
            await self.publish_pcm(pcm)

        agent._publish_pcm = bound_publish
        await agent.run()

    async def disconnect(self) -> None:
        for stream in self._remote_streams:
            await stream.aclose()
        if self._room:
            await self._room.disconnect()
```

#### Step 5 — Token endpoint

Create `app/routers/livekit_token.py`.

```python
"""LiveKit token endpoint — browser and SIP clients join rooms with these tokens."""

from fastapi import APIRouter, Query
from app.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from app.transports.livekit import _generate_token

router = APIRouter(prefix="/livekit", tags=["livekit"])


@router.get("/token")
async def get_token(
    room: str = Query(default="main"),
    identity: str = Query(default="browser-user"),
) -> dict:
    """Return a LiveKit access token for a client to join a room."""
    token = _generate_token(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, room, identity)
    return {"token": token, "wsUrl": LIVEKIT_URL}
```

#### Step 6 — SIP worker

Create `app/routers/livekit_sip_worker.py`.

```python
"""
LiveKit SIP inbound worker.

Run as: LIVEKIT_SIP_ROOM=sip-call python -m app.routers.livekit_sip_worker

LiveKit SIP automatically creates rooms when SIP calls arrive
(determined by dispatch rules in livekit-infra.valura.co.in).
This process connects to those rooms as the agent.
"""

import asyncio
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from app.transports.livekit import LiveKitTransport
from app.providers.tts import SarvamTTSProvider
from app.providers.stt import SarvamSTTProvider
from app.providers.llm import SarvamLLMProvider
from app.agent import VoiceAgent


async def main() -> None:
    room_name = os.getenv("LIVEKIT_SIP_ROOM", "sip-call")

    tts = SarvamTTSProvider()
    stt = SarvamSTTProvider()
    llm = SarvamLLMProvider()

    transport = LiveKitTransport(room_name=room_name, agent_identity="voice-agent")
    await transport.connect()
    print(f"[LiveKit] Agent connected to room: {room_name}")

    async def audio_gen():
        async for chunk in transport.audio_source():
            yield chunk

    agent = VoiceAgent(
        audio_source=audio_gen,
        tts_provider=tts,
        stt_provider=stt,
        llm_provider=llm,
    )

    try:
        await transport.run_agent(agent)
    except KeyboardInterrupt:
        pass
    finally:
        await transport.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

#### Step 7 — Mount in main.py

Update `app/main.py` to mount the LiveKit token router alongside existing Plivo routers.

```python
"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.plivo_webhook import router as plivo_router  # REMOVE in Phase 3
from app.routers.telephony import router as plivo_ws_router   # REMOVE in Phase 3
from app.routers.livekit_token import router as livekit_router  # ADD in M1

app = FastAPI(title="Voice AI")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(plivo_router)    # REMOVE in Phase 3
app.include_router(plivo_ws_router)  # REMOVE in Phase 3
app.include_router(livekit_router)   # ADD in M1


@app.get("/")
async def root():
    return {"service": "voice-ai", "routers": ["plivo", "livekit"]}


if __name__ == "__main__":
    import uvicorn
    from app.config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
```

---

## 6. M2 — Call State + Language + KB Tool

**Goal:** Turn the demo into a support-shaped agent with session memory, multilingual support, and a first tool (KB search).

**Exit criteria:**
- [ ] Session keeps call + language state across turns
- [ ] Hinglish utterance gets a coherent reply
- [ ] KB tool path works end-to-end with mock orchestrator
- [ ] Advice questions are refused without crashing the loop
- [ ] Unit/integration tests for: language switch, KB tool request shape, advice refusal

### M2 Build

#### Step 1 — Session state machine

Create `app/session.py`.

```python
"""Call session — state machine, language state, conversation context."""

from enum import Enum
from app.agents.reasoner import ConversationHistory

class CallState(str, Enum):
    GREETING   = "greeting"
    LISTENING  = "listening"
    UNDERSTANDING = "understanding"
    RESPONSE   = "response"
    CALL_END   = "call_end"
    POLICY_BLOCK = "policy_block"
    AUTH_REQUIRED = "auth_required"

class Language(str, Enum):
    ENGLISH  = "en"
    HINDI    = "hi"
    HINGLISH = "hinglish"
    UNKNOWN  = "unknown"

LAN_SWITCH_PHRASES = {
    "hinglish": ["bol", "batana", " batao", " bolo", "hindi mein", "हिंदी में"],
    "english": ["in english", "speak in english", "english mein"],
}

class CallSession:
    """
    Maintains state across a single call.

    State machine: GREETING → LISTENING ↔ UNDERSTANDING ↔ RESPONSE → LISTENING ...
    """

    def __init__(
        self,
        call_id: str,
        from_number: str,
        to_number: str,
        system_prompt: str | None = None,
        kb_client = None,
        max_tool_calls: int = 4,
    ):
        self.call_id = call_id
        self.from_number = from_number
        self.to_number = to_number
        self.state = CallState.GREETING
        self.language = Language.ENGLISH
        self._history = ConversationHistory(system_prompt=system_prompt)
        self._kb_client = kb_client
        self._tool_calls_this_turn = 0
        self._tool_calls_total = 0
        self._max_tool_calls = max_tool_calls
        self._exit_requested = False

    def detect_language(self, text: str) -> Language:
        """
        Simple heuristic: check for Hindi script or romanized Hindi patterns.
        """
        HAS_HINDI = any("\u0900" <= c <= "\u097F" for c in text)
        ENGLISH_WORDS = sum(1 for w in text.split() if w.isascii())
        TOTAL_WORDS = len(text.split())
        EN_RATIO = ENGLISH_WORDS / max(TOTAL_WORDS, 1)

        if HAS_HINDI:
            return Language.HINDI if EN_RATIO < 0.3 else Language.HINGLISH
        if EN_RATIO < 0.5:
            return Language.HINGLISH
        return Language.ENGLISH

    def maybe_switch_language(self, text: str) -> None:
        t = text.lower()
        for lang, phrases in LAN_SWITCH_PHRASES.items():
            if any(p.lower() in t for p in phrases):
                self.language = Language(lang)
                print(f"[Session] Language switched to {lang}")

    def handle_exit(self, text: str) -> bool:
        if self._history.is_exit(text):
            self.state = CallState.CALL_END
            self._exit_requested = True
            return True
        return False

    def kb_search(self, query: str) -> str | None:
        if not self._kb_client:
            return None
        if self._tool_calls_total >= self._max_tool_calls:
            return None
        self._tool_calls_this_turn += 1
        self._tool_calls_total += 1
        try:
            return self._kb_client.search(query)
        except Exception as e:
            print(f"[KB] Search failed: {e}")
            return None

    def reset_tool_budget(self) -> None:
        self._tool_calls_this_turn = 0

    def end_turn(self) -> None:
        self.reset_tool_budget()
        self.state = CallState.LISTENING
```

#### Step 2 — KB tool client

Create `app/services/kb_client.py`.

```python
"""HTTP client to Voice Orchestrator for KB search."""

import os
from typing import Any

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001").rstrip("/")

class KBClient:
    """Client for the Voice Orchestrator's support KB."""

    def __init__(self, base_url: str = ORCHESTRATOR_URL, timeout: float = 5.0):
        self.base_url = base_url
        self.timeout = timeout

    async def search(self, query: str) -> str | None:
        """Search the support KB. Returns snippet or None."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/kb/search",
                    json={"query": query},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data.get("answer") or data.get("snippet")
        except Exception:
            return None

# Mock for local dev without orchestrator
class MockKBClient:
    async def search(self, query: str) -> str | None:
        kb = {
            "account": "You can check your account balance in the app under Profile > Account Details.",
            "password": "To reset your password, go to Settings > Security > Reset Password.",
            "loan": "For loan inquiries, please contact our loans team at loans@example.com.",
        }
        q = query.lower()
        for key, val in kb.items():
            if key in q:
                return val
        return None
```

#### Step 3 — Update VoiceAgent for M2

Add session, language detection, and KB tool integration.

```python
# In app/agent.py, add to VoiceAgent.__init__:
def __init__(
    self,
    audio_source,
    tts_provider,
    session: CallSession,  # NEW — replaces raw history
    stt_provider=None,
    llm_provider=None,
):
    self._session = session
    # ... rest unchanged

# In VoiceAgent.run(), replace _history.ask() with:
async def run(self) -> None:
    self._running = True
    await self.greet()

    while self._running:
        pcm = await self._read_utterance()
        if pcm is None:
            break

        result = self._stt.transcribe(_amplify(pcm))
        if not result.text.strip():
            continue

        text = result.text
        print(f"[Agent] user: {text}")

        self._session.maybe_switch_language(text)
        if self._session.handle_exit(text):
            await self._speak("Goodbye! Have a great day.")
            break

        # KB search via tool call
        kb_answer = self._session.kb_search(text)
        if kb_answer:
            await self._speak(kb_answer)
        else:
            reply = self._session._history.ask(text)
            print(f"[Agent] AI: {reply}")
            await self._speak(reply)

        await asyncio.sleep(0.3)

# Greeting in the session's language
async def greet(self) -> None:
    if self._greeting_done:
        return
    greeting = {
        Language.ENGLISH: "Hello! How can I help you today?",
        Language.HINDI: "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?",
        Language.HINGLISH: "Namaste! Aapki kaise madad kar sakta hoon?",
    }.get(self._session.language, "Hello! How can I help you today?")
    await self._speak(greeting)
    self._greeting_done = True
    await asyncio.sleep(0.3)
```

---

## 7. M3 — Policy Skeleton + Reliability

**Goal:** Make the worker production-safe. Policy gate, timeouts, fallbacks, circuit breakers, tool budget, idempotency keys.

**Exit criteria:**
- [ ] No tool runs without passing the policy gate
- [ ] Provider timeout → fallback or graceful "please repeat" path
- [ ] Tool budget enforced; no infinite tool loops
- [ ] Idempotency key always set on mutating tool request payloads
- [ ] Docs updated: how to run M1–M3 locally + what "done" means for PR review

### M3 Build

#### Step 1 — Policy gate

Create `app/policy.py`.

```python
"""Policy gate — intercepts LLM tool calls before they reach the orchestrator."""

from enum import Enum
from typing import Any

class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    BLOCK = "block"

SENSITIVE_TOPICS = {
    "investment", "stock", "mutual fund", "fd", "fixed deposit",
    "loan", "credit", "lend", "borrow",
    "mpin", "pin change", "password change", "reset password",
}

BLOCK_PHRASES = {
    "i can't help with that": PolicyDecision.BLOCK,
}

class PolicyGate:
    """
    Policy gate for the voice agent.

    Runs before any tool call or before a sensitive reply is spoken.
    """

    def check_tool(self, tool_name: str, arguments: dict) -> PolicyDecision:
        """
        Called before a tool is invoked.
        Tools are only called after this returns ALLOW.
        """
        if tool_name in {"create_ticket", "update_ticket", "otp", "refund"}:
            return PolicyDecision.BLOCK  # requires auth
        return PolicyDecision.ALLOW

    def check_text(self, text: str) -> PolicyDecision:
        """
        Called before TTS. Refuse advice/investment topics.
        """
        t = text.lower()
        if any(topic in t for topic in SENSITIVE_TOPICS):
            return PolicyDecision.BLOCK
        return PolicyDecision.ALLOW

    def allow_message(self) -> str:
        return "I'm not able to help with that. Please contact our team for assistance with sensitive matters."

    def block_message(self) -> str:
        return "I need to verify your identity before I can help with that. Please contact our support team."
```

#### Step 2 — Resilience

Create `app/resilience.py`.

```python
"""Resilience primitives — circuit breaker, timeouts, fallback."""

import asyncio
import time
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")

class CircuitState(str, Enum):
    CLOSED = "closed"     # Normal operation
    OPEN   = "open"       # Failing — fast-reject
    HALF   = "half"       # Testing — one probe request

REQUESTS_BEFORE_OPEN = 5
FAILURE_THRESHOLD    = 3
RECOVERY_TIMEOUT_S   = 30.0

class CircuitBreaker:
    """
    Circuit breaker for external service calls (STT, LLM, TTS).

    CLOSED → OPEN (after FAILURE_THRESHOLD failures in REQUESTS_BEFORE_OPEN requests)
    OPEN → HALF (after RECOVERY_TIMEOUT_S seconds)
    HALF → CLOSED (if probe succeeds) or OPEN (if it fails)
    """

    def __init__(self, name: str):
        self.name = name
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time = 0.0
        self._last_open_time = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_open_time >= RECOVERY_TIMEOUT_S:
                self._state = CircuitState.HALF
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        if self._state == CircuitState.HALF:
            self._state = CircuitState.CLOSED
            print(f"[CircuitBreaker] {self.name}: CLOSED (recovered)")

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF:
            self._state = CircuitState.OPEN
            self._last_open_time = self._last_failure_time
            print(f"[CircuitBreaker] {self.name}: OPEN (half-open probe failed)")
        elif self._failures >= FAILURE_THRESHOLD:
            self._state = CircuitState.OPEN
            self._last_open_time = self._last_failure_time
            print(f"[CircuitBreaker] {self.name}: OPEN (threshold reached)")

    def can_execute(self) -> bool:
        return self.state != CircuitState.OPEN

async def with_timeout(coro: T, timeout_s: float, label: str = "call") -> T:
    """Run a coroutine with a timeout. Raises asyncio.TimeoutError on timeout."""
    return await asyncio.wait_for(coro, timeout=timeout_s)

async def with_circuit(circuit: CircuitBreaker, coro, fallback=None):
    """Execute within a circuit breaker."""
    if not circuit.can_execute():
        print(f"[CircuitBreaker] {circuit.name}: OPEN — using fallback")
        if fallback:
            return await fallback()
        raise RuntimeError(f"Circuit {circuit.name} is OPEN")
    try:
        result = await coro
        circuit.record_success()
        return result
    except Exception as e:
        circuit.record_failure()
        if fallback:
            return await fallback()
        raise
```

#### Step 3 — Update VoiceAgent for M3

Integrate policy gate, circuit breakers, timeouts, and idempotency keys.

```python
# In app/agent.py VoiceAgent.__init__:
def __init__(
    self,
    audio_source,
    tts_provider,
    session: CallSession,
    stt_provider=None,
    llm_provider=None,
    stt_circuit: CircuitBreaker | None = None,
    llm_circuit: CircuitBreaker | None = None,
    tts_circuit: CircuitBreaker | None = None,
    policy_gate: PolicyGate | None = None,
):
    self._stt_circuit = stt_circuit or CircuitBreaker("stt")
    self._llm_circuit = llm_circuit or CircuitBreaker("llm")
    self._tts_circuit = tts_circuit or CircuitBreaker("tts")
    self._policy = policy_gate or PolicyGate()

# In VoiceAgent.run(), wrap STT/LLM/TTS calls:
async def run(self) -> None:
    self._running = True
    await self.greet()
    while self._running:
        pcm = await self._read_utterance()
        if pcm is None:
            break
        try:
            result = await with_circuit(
                self._stt_circuit,
                with_timeout(
                    asyncio.to_thread(self._stt.transcribe, _amplify(pcm)),
                    timeout_s=10.0, label="STT",
                ),
                fallback=lambda: None,
            )
        except asyncio.TimeoutError:
            await self._speak("I'm sorry, I didn't catch that. Could you please repeat?")
            continue

        if not result or not result.text.strip():
            continue

        text = result.text
        self._session.maybe_switch_language(text)
        if self._session.handle_exit(text):
            await self._speak("Goodbye!")
            break

        # LLM call with circuit breaker + timeout
        try:
            reply = await with_circuit(
                self._llm_circuit,
                with_timeout(
                    asyncio.to_thread(self._session._history.ask, text),
                    timeout_s=15.0, label="LLM",
                ),
                fallback=lambda: "I'm having trouble thinking right now. Could you repeat that?",
            )
        except asyncio.TimeoutError:
            reply = "I'm having trouble thinking right now. Could you repeat that?"

        print(f"[Agent] AI: {reply}")

        # Policy check before TTS
        policy_decision = self._policy.check_text(reply)
        if policy_decision == PolicyDecision.BLOCK:
            reply = self._policy.block_message()
        elif policy_decision == PolicyDecision.DENY:
            reply = self._policy.allow_message()

        await self._speak(reply)
        await asyncio.sleep(0.3)

# Idempotency keys on tool calls
def kb_search_with_idempotency(kb_client, query: str, call_id: str) -> str | None:
    import hashlib, json
    payload = json.dumps({"query": query}, sort_keys=True)
    idempotency_key = hashlib.sha256(
        f"{call_id}:kb_search:{payload}".encode()
    ).hexdigest()[:32]
    # Pass idempotency_key in headers when calling orchestrator
    return kb_client.search(query, idempotency_key=idempotency_key)
```

---

## 8. LiveKit Infrastructure Migration (Phase 1–3)

These steps configure the LiveKit server and Plivo to route SIP calls through LiveKit. No code changes needed for the infrastructure side.

### Phase 1 — LiveKit transport code (M1, parallel)

Add to `.env.example`:

```env
# LiveKit (self-hosted)
LIVEKIT_URL=wss://livekit-infra.valura.co.in
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_SIP_ROOM=sip-call

# Plivo (existing — stays until Phase 3)
PLIVO_AUTH_ID=
PLIVO_AUTH_TOKEN=
PLIVO_CALLER_NUMBER=
```

Add to `app/config/__init__.py`:

```python
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "").strip()
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "").strip()
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "").strip()
LIVEKIT_SIP_ROOM = os.getenv("LIVEKIT_SIP_ROOM", "sip-call").strip()
```

### Phase 2 — Configure Plivo → LiveKit SIP

#### 2A — Plivo Console

1. **SIP Trunking → Inbound Trunks → Create Trunk**
   - Name: `livekit-trunk`
   - Primary URI: `YOUR_PROJECT.sip.livekit.cloud;transport=tcp`
     (find your SIP endpoint in `livekit-infra.valura.co.in` → Project Settings → SIP URI)
   - Link Numbers: `+918031728909`

2. **Numbers → Update `+918031728909`**
   - Application Type: SIP trunking
   - SIP Trunk: `livekit-trunk`

#### 2B — LiveKit Console (livekit-infra.valura.co.in)

1. **Telephony → SIP → Inbound Trunks → Create**
   - Name: `plivo-inbound`
   - Numbers: `["+918031728909"]`
   - Allowed Addresses: Plivo's SIP server IPs (or leave open for testing)

2. **Telephony → SIP → Dispatch Rules → Create**
   - Room Name Template: `sip-call`
   - Trunk: `plivo-inbound`

3. **Telephony → SIP → Outbound Trunks → Create** (for outbound calls)
   - Name: `plivo-outbound`
   - Address: `<your-plivo-account-id>.zt.plivo.com`
   - Numbers: `["+918031728909"]`
   - Auth Username / Auth Password: from Plivo's SIP credentials

#### 2C — Test

1. Call `+918031728909`
2. Plivo → LiveKit SIP → room `sip-call`
3. `livekit_sip_worker.py` picks up room → VoiceAgent runs
4. Caller hears greeting → speaks → agent responds

### Phase 3 — Remove Plivo (after M1–M3 + LiveKit SIP confirmed)

```bash
rm app/routers/plivo_webhook.py
rm app/routers/telephony.py
rm app/controllers/inbound.py
rm app/controllers/outbound.py
rm app/controllers/hangup.py
rm app/controllers/telephony_controller.py
rm app/services/plivo_client.py
rm app/config/plivo.py
```

Remove from `app/services/mongo_logging.py`:
- Plivo billing fields (`call_cost`, `call_duration`, etc.)

Remove from `app/config/__init__.py`:
- `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_CALLER_NUMBER`
- `VOICE_MODE`, `LEADING_SILENCE_MS`, `PRE_SPEECH_MS`, `MIN_SPEECH_MS`

---

## 9. Adding New Telephony Providers

With LiveKit as the hub, adding Exotel (or any SIP provider) takes minutes and **zero code changes**:

1. **Exotel Console** → set SIP trunk destination to LiveKit's SIP endpoint
2. **LiveKit Console → SIP → Inbound Trunks → Create**
   - Name: `exotel-inbound`
   - Numbers: `["+91XXXXXXXXXX"]`
3. **LiveKit Console → SIP → Dispatch Rules → Create**
   - Room Name Template: `exotel-call`
   - Trunk: `exotel-inbound`
4. Set `LIVEKIT_SIP_ROOM=exotel-call` and run `livekit_sip_worker.py`

---

## 10. Final File Map

| File | Milestone | Action |
|---|---|---|
| `requirements.txt` | M1 | Add `livekit>=1.0` |
| `.env.example` | M1 | Add `LIVEKIT_*` vars |
| `app/config/__init__.py` | M1 | Add `LIVEKIT_*` config |
| `app/providers/__init__.py` | M1 | **New** — package init |
| `app/providers/stt.py` | M1 | **New** — `STTProvider` + `SarvamSTTProvider` |
| `app/providers/tts.py` | M1 | **New** — `TTSProvider` + `SarvamTTSProvider` |
| `app/providers/llm.py` | M1 | **New** — `LLMProvider` + `SarvamLLMProvider` |
| `app/agent.py` | M1 | **New** — transport-agnostic voice AI |
| `app/transports/__init__.py` | M1 | **New** — package init |
| `app/transports/livekit.py` | M1 | **New** — LiveKit Core SDK transport |
| `app/transports/browser.py` | M1 | **New** — browser WS transport (local dev) |
| `app/services/sarvam_tts.py` | M1 | **New** — extract TTS from telephony_controller |
| `app/routers/livekit_token.py` | M1 | **New** — token endpoint |
| `app/routers/livekit_sip_worker.py` | M1 | **New** — SIP inbound worker |
| `app/main.py` | M1 | Mount `livekit_router` |
| `app/session.py` | M2 | **New** — `CallSession` state machine |
| `app/services/kb_client.py` | M2 | **New** — KB search client + mock |
| `app/policy.py` | M3 | **New** — `PolicyGate` |
| `app/resilience.py` | M3 | **New** — circuit breaker + timeouts |
| `app/routers/plivo_webhook.py` | Phase 3 | **Delete** |
| `app/routers/telephony.py` | Phase 3 | **Delete** |
| `app/controllers/inbound.py` | Phase 3 | **Delete** |
| `app/controllers/outbound.py` | Phase 3 | **Delete** |
| `app/controllers/hangup.py` | Phase 3 | **Delete** |
| `app/controllers/telephony_controller.py` | Phase 3 | **Delete** |
| `app/services/plivo_client.py` | Phase 3 | **Delete** |
| `app/config/plivo.py` | Phase 3 | **Delete** |

---

## 11. Running Everything

```bash
# ─── Terminal 1: FastAPI server ───────────────────────────────────────────
python app/main.py

# ─── Terminal 2: SIP inbound worker (Plivo/Exotel calls arrive here) ─────
LIVEKIT_SIP_ROOM=sip-call python -m app.routers.livekit_sip_worker

# ─── Browser: test locally ────────────────────────────────────────────────
# GET /livekit/token?room=main&identity=alice
# Returns: { token: "<jwt>", wsUrl: "wss://livekit-infra.valura.co.in" }
# Use livekit-client SDK to connect with this token
```

**Migration dependency chain:**
```
M1 code (LiveKit transport)
    ↓
M1 tested (browser calls work)
    ↓
Phase 2 (Plivo → LiveKit SIP configured)
    ↓
M2 (session + KB)
    ↓
M3 (policy + resilience)
    ↓
Phase 3 (Plivo deleted)
```
