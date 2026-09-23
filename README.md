# Voice-AI

A production-ready voice AI server for real phone calls, powered by **Sarvam AI** (STT, LLM, TTS) with **Plivo** telephony integration today and **LiveKit** as the planned central hub for multi-provider telephony.

---

## Current Architecture

```
PSTN caller
    │
    ▼
Plivo Cloud (telephony provider — SIP + REST)
    │
    ├─── HTTP POST /call/incoming ──────────────────► FastAPI
    │                                               ├── InboundController → XML <Stream>
    │                                               └── Plivo WebSocket /stream
    │
    └─── WebSocket /stream ─────────────────────────► TelephonyController
                                                        │
                                                        ├── μ-law → Linear16 PCM decode
                                                        ├── Amplify (AGC)
                                                        │
                                                        ├── VAD (webrtcvad)
                                                        │    └── segments speech into utterances
                                                        │
                                                        ├── STT (Sarvam Saaras v3)
                                                        │    └── PCM bytes → text transcript
                                                        │
                                                        ├── LLM (Sarvam-105B, OpenAI-compatible)
                                                        │    └── conversation history + user text → reply
                                                        │
                                                        ├── TTS (Sarvam Bulbul v3)
                                                        │    └── reply text → raw PCM
                                                        │
                                                        └── WebSocket playAudio frames ──► Plivo
                                                            │
                                                            ▼
                                                        PSTN caller hears TTS
```

### What this pipeline does today

1. A phone call comes in via Plivo → Plivo POSTs to `/call/incoming`
2. `InboundController` returns Plivo XML with a `<Stream>` element pointing to our WebSocket
3. `TelephonyController` opens the Plivo WebSocket and begins the voice loop:
   - Decodes μ-law audio from Plivo into 16-bit PCM
   - Amplifies PCM via AGC for consistent volume
   - Feeds PCM through `webrtcvad` to detect speech boundaries
   - On silence, assembles the utterance and sends it to **Sarvam STT**
   - Calls **Sarvam LLM** with the transcript + conversation history
   - Synthesizes the reply with **Sarvam TTS** and streams PCM back over the WebSocket as `playAudio` frames
4. Plivo plays the audio to the caller

---

## Project Structure

```
Voice-AI/
├── app/
│   ├── main.py                      # FastAPI entry point — mounts all routers
│   │
│   ├── config/
│   │   ├── __init__.py              # All env vars in one place (Sarvam, Plivo, VAD, voice)
│   │   ├── settings.py              # Re-exports voice/agent settings
│   │   ├── voice.py                 # VAD aggressiveness, sample rate, silence thresholds
│   │   ├── sarvam.py                # Sarvam credential builder (headers for STT + chat)
│   │   └── plivo.py                 # Plivo auth_id / auth_token loader
│   │
│   ├── core/                        # Pure-stdlib utilities — no external I/O
│   │   ├── audio_io.py              # PCM → WAV container (in-memory)
│   │   ├── http.py                  # Exponential-backoff POST with retry
│   │   └── text.py                 # Markdown stripper (TTS-friendly output)
│   │
│   ├── models/                      # Pydantic schemas for all request/response shapes
│   │   ├── audio.py                # Utterance (PCM bytes + sample rate + duration)
│   │   ├── messages.py             # Message (role + content, to_openai_dict())
│   │   ├── transcript.py           # Transcript (text + language + confidence)
│   │   ├── credentials.py          # SarvamCredentials / PlivoCredentials
│   │   ├── inbound.py              # Plivo inbound call webhook fields
│   │   ├── hangup.py               # Plivo hangup webhook fields
│   │   ├── outbound.py             # Outbound call request / response
│   │   ├── plivo.py               # Full Plivo data shapes
│   │   └── telephony.py            # CallContext from Plivo WebSocket query params
│   │
│   ├── services/                    # External I/O — one module per integration
│   │   ├── sarvam_stt.py         # POST /speech-to-text → Transcript (billed per second)
│   │   ├── sarvam_chat.py        # POST /v1/chat/completions → reply (Sarvam-105B)
│   │   ├── plivo_client.py       # Plivo Calls API — make_call(), hangup_call()
│   │   └── mongo_logging.py      # MongoDB persistence — call metadata + billing on hangup
│   │
│   ├── agents/
│   │   └── reasoner.py           # ConversationHistory (rolling context) + ask() → LLM
│   │
│   ├── controllers/                # Business logic — orchestrate services
│   │   ├── inbound.py            # Plivo inbound webhook → returns <Stream> XML
│   │   ├── outbound.py           # Plivo outbound via plivo_client.make_call()
│   │   ├── hangup.py            # Plivo hangup webhook → mongo_logger.add_hangup()
│   │   └── telephony_controller.py  # Full voice loop: decode → VAD → STT → LLM → TTS
│   │
│   └── routers/                   # FastAPI APIRouter instances
│       ├── plivo_webhook.py      # POST /call/incoming · /call/hangup · /call/outbound
│       └── telephony.py          # WebSocket /stream · GET /health
│
├── PLAN-LiveKit-Migration.md       # Full migration plan: Plivo → LiveKit hub + M1–M3
├── Plan-voiceagent.md              # Voice agent milestones M1–M3 (state, KB, policy)
├── PRICING.md                      # Detailed Sarvam cost breakdown + telephony pricing
├── requirements.txt                # Python dependencies
├── .env.example                    # Template for all env vars (committed)
└── .env                            # Real keys (gitignored)
```

---

## Current Status

| Component | Status | Notes |
|---|---|---|
| Plivo inbound calls | ✅ Working | `<Stream>` XML → WebSocket → voice loop |
| Plivo outbound calls | ✅ Working | `POST /call/outbound` → Plivo API |
| Plivo hangup webhook | ✅ Working | MongoDB logging of call metadata + billing |
| Sarvam STT (Saaras v3) | ✅ Working | Billed per second of audio uploaded |
| Sarvam LLM (Sarvam-105B) | ✅ Working | OpenAI-compatible endpoint |
| Sarvam TTS (Bulbul v3) | ✅ Working | PCM streamed over Plivo WebSocket |
| VAD (webrtcvad) | ✅ Working | Segments speech into utterances |
| AGC (Amplify) | ✅ Working | Applied to incoming PCM before STT |
| μ-law decoding | ✅ Working | Plivo streams μ-law; decoded before VAD/STT |
| Sequential TTS/STT | ✅ Working | TTS plays first, then STT listens (avoids AEC) |
| MongoDB logging | ✅ Working | Call metadata + Plivo billing data on hangup |
| LiveKit integration | 🔴 Not started | Planned — see `PLAN-LiveKit-Migration.md` |
| Provider interfaces (STT/LLM/TTS) | 🔴 Not started | Planned for M1 — enables Sarvam↔Deepgram swap |
| VoiceAgent (transport-agnostic) | 🔴 Not started | Planned for M1 |
| Session state + language | 🔴 Not started | Planned for M2 |
| KB tool + policy gate | 🔴 Not started | Planned for M2–M3 |
| Circuit breakers + reliability | 🔴 Not started | Planned for M3 |

---

## Requirements

- **Python 3.10+**
- **Plivo account** with an active phone number and API credentials (`auth_id` + `auth_token`)
- **Sarvam AI account** with API key and subscription key from [dashboard.sarvam.ai](https://dashboard.sarvam.ai)
- **Public URL** — Plivo needs to reach your server via HTTPS. Use ngrok for local development:

```bash
# Terminal 1 — keep ngrok running
ngrok http 5000

# Terminal 2 — start the server with the ngrok URL
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

Then configure your Plivo number's **Answer URL** in the Plivo console to:
`https://<your-ngrok-id>.ngrok-free.app/call/incoming`

---

## Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Create .env from the template and fill in your keys
cp .env.example .env
# then edit .env with your real Plivo and Sarvam credentials
```

### Running the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

### Testing an outbound call

```bash
curl -X POST http://localhost:5000/call/outbound \
  -H "Content-Type: application/json" \
  -d '{"destination_number": "+919876543210"}'
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check (also WebSocket) |
| `POST` | `/call/incoming` | Plivo inbound call webhook — returns `<Stream>` XML |
| `POST` | `/call/hangup` | Plivo hangup webhook — logs to MongoDB |
| `POST` | `/call/outbound` | Initiates outbound call via Plivo API |
| `WS` | `/stream` | Plivo audio WebSocket — voice loop |
| `GET` | `/debug/xml` | Returns the current inbound XML response for debugging |

---

## Configuration

All settings live in `.env`. See `.env.example` for every available variable.

### Voice / VAD tuning

| Env var | Default | Description |
|---|---|---|
| `SAMPLE_RATE` | `16000` | Audio sample rate (Hz). Must be 8k/16k/32k/48k for `webrtcvad`. |
| `VAD_AGGRESSIVENESS` | `3` | 0–3. Higher = stricter speech detection (better for noisy environments). |
| `SILENCE_END_MS` | `400` | Trailing silence that ends a turn. Lower = snappier but may clip mid-thought pauses. |
| `MAX_UTTERANCE_MS` | `60000` | Hard cap per utterance (safety net). |
| `PRE_SPEECH_MS` | `200` | Audio kept before the first voiced frame, prevents first-word clipping. |

### Sarvam

| Env var | Description |
|---|---|
| `SARVAM_API_KEY` | Your Sarvam API key (from dashboard.sarvam.ai) |
| `SARVAM_SUBSCRIPTION_KEY` | Your `api-subscription-key` (same as API key in most cases) |
| `SARVAM_STT_MODEL` | STT model — default `saaras:v3` |
| `SARVAM_TTS_MODEL` | TTS model — default `bulbul:v3` |
| `SARVAM_TTS_VOICE` | TTS speaker voice — default `shubh` |
| `SARVAM_LANGUAGE_CODE` | BCP-47 language code for STT and TTS — default `en-IN` |
| `SARVAM_CHAT_MODEL` | LLM model — default `sarvam-105b` |
| `SYSTEM_PROMPT` | Instructions to the LLM |

### Plivo

| Env var | Description |
|---|---|
| `PLIVO_AUTH_ID` | Plivo Auth ID |
| `PLIVO_AUTH_TOKEN` | Plivo Auth Token |
| `PLIVO_CALLER_NUMBER` | Plivo number to use for outbound calls (E.164, e.g. `+918031728909`) |

---

## Known Issues & Fixes Applied

| Issue | Root Cause | Fix |
|---|---|---|
| Call hangs up with "End Of XML Instructions" (4010) | `<Stream>` XML had `url=` attribute and `maxDuration=` instead of text content and `streamTimeout=` | XML corrected to spec-compliant format |
| Call hangs up immediately with "Invalid Answer XML" | `InboundController` returned `<Speak>Please wait.</Speak>` for all call states | Always return `<Stream>` XML on `CallStatus=answered` |
| TTS plays for a split second then cuts off | `streamId` empty in `playAudio` frames (TTS sent before Plivo `start` event arrived) | `run_async()` now waits for `_stream_id` to be set |
| TTS plays but STT never captures user speech | Plivo's AEC aggressively suppressed caller audio during TTS | TTS and STT run strictly sequentially; AEC settles for 300ms after TTS |
| STT returns empty with `rms=0.0` | `_read_utterance()` was trimming leading silence that contained speech | Trim block removed; `_amplify()` now applied to assembled utterance, not per-frame |
| STT returns 400 Bad Request | `Content-Type: application/json` in headers when sending `multipart/form-data` for STT | Removed `Content-Type` override from `subscription_headers` |

---

## Cost

See [`PRICING.md`](PRICING.md) for the full breakdown. Summary:

| Component | Per minute of conversation |
|---|---|
| STT (Saaras v3) — ~64s of speech captured | ₹0.53 |
| TTS (Bulbul v3) | ₹0.01 |
| LLM (Sarvam-105B) | ~₹0.00004 |
| **Total** | **≈ ₹0.55/min** |

STT is ~98% of the bill. The LLM cost is negligible for voice workloads. Every new Sarvam account comes with ₹100 free credits — roughly 3 hours of conversation.

---

## Future: LiveKit as Central Hub

The current Plivo integration works but is Plivo-specific. Adding Exotel, Twilio, or any other telephony provider would require duplicating all the webhook, WebSocket, and audio protocol code.

The migration plan in [`PLAN-LiveKit-Migration.md`](PLAN-LiveKit-Migration.md) replaces this with **LiveKit** as a transport-agnostic hub:

```
PSTN caller
    │
    ▼
Plivo / Exotel / Twilio / any SIP provider
    │  ← SIP INVITE
    ▼
LiveKit (self-hosted)
    │  ← SIP B2BUA — bridges PSTN ↔ WebRTC
    ▼
LiveKit Room
    ├── SIP participant (PSTN caller — audio via SIP)
    └── Our agent (WebRTC participant — audio via LiveKit Core SDK)
              │
              ├── AudioStream ──► VAD ──► STT ──► LLM ──► TTS
              └── AudioSource ◄──────────────────────────────────
```

With LiveKit as the hub, adding a new telephony provider = configure it in the LiveKit console. **Zero code changes.**

The plan covers:
- **M1** — LiveKit transport + voice agent (browser test first, no SIP)
- **M2** — Session state, language detection, KB tool via orchestrator
- **M3** — Policy gate, circuit breakers, timeouts, tool budget
- **Phase 2** — Configure Plivo → LiveKit SIP (parallel with M1)
- **Phase 3** — Delete all Plivo-specific code

---

## Troubleshooting

**Call hangs up immediately after connecting**
: Check the `<Stream>` XML being returned by `/call/incoming`. It must use `streamTimeout=` (not `maxDuration=`), place the WebSocket URL as text content (not a `url=` attribute), and include `bidirectional="true" keepCallAlive="true"`.

**I hear TTS but my voice isn't being transcribed**
: This is most likely Plivo's Acoustic Echo Cancellation (AEC). TTS and STT run sequentially in the current code — if TTS is still playing when you speak, AEC will suppress your audio. Wait 300ms after TTS finishes before speaking.

**STT returns empty transcripts**
: Check that the PCM being sent to Sarvam is valid 16kHz mono audio. Run the server with logging enabled and look for `rms=`, `max=`, `min=` in the output — if all zeros, the audio never arrived from Plivo. Also verify `SARVAM_API_KEY` and `SARVAM_SUBSCRIPTION_KEY` are both set correctly.

**Plivo returns 4010 "End Of XML Instructions"**
: The WebSocket URL in the XML is malformed. Ensure the URL has no double protocol prefix (`wss://https://...`). The URL must be accessible from the public internet.

**`ModuleNotFoundError: No module named 'app'`**
: Run the server from the project root: `python -m app.main` or `uvicorn app.main:app`. Do not run `python app/main.py` from within the `app/` directory.

**`SARVAM_API_KEY is missing`**
: `.env` doesn't exist or still has the placeholder. Copy from `.env.example` and fill in your real Sarvam API key.
