# Voice-AI

A voice-driven AI assistant that listens to your microphone, talks to Sarvam's
APIs, and replies out loud. Built as a single self-contained Python script.

The pipeline is intentionally small: every step (STT, chat, TTS) is one
Sarvam API call, with a long-lived microphone stream and voice-activity
detection in between so the loop feels like a real assistant.

---

## Pipeline

```
   you speak                  Saaras v3                  Sarvam-105B                 Bulbul v3
   ────────►  ┌──────────┐  ────────►  ┌──────────┐  ────────►  ┌──────────┐  ────────►  ┌──────────┐  ────────►  you hear it
              │ PyAudio  │             │ /speech- │             │ /v1/chat │             │ /text-to │
              │ +VAD mic │             │  to-text │             │ /complet.│             │  -speech │
              └──────────┘             └──────────┘             └──────────┘             └──────────┘
```

| Stage | What it does | Sarvam endpoint |
|---|---|---|
| Capture | Long-lived 16 kHz mic stream; `webrtcvad` segments speech from silence | — |
| STT | Transcribe each utterance | `POST /speech-to-text` (`saaras:v3`) |
| Chat | Generate a short reply, with rolling conversation context | `POST /v1/chat/completions` (`sarvam-105b`) |
| TTS | Synthesize the reply and play it through `afplay` | `POST /text-to-speech` (`bulbul:v3`) |

---

## Features

- **Voice-activity detection.** `webrtcvad` listens for end-of-speech; no
  fixed-duration windows, no clipped sentences, no empty transcripts.
- **Single open mic stream.** Microphone is opened once at startup and stays
  open across turns — eliminates the open/close race with `afplay` and keeps
  latency low.
- **Pre-roll buffer.** The first 300 ms before a voiced frame is kept so the
  first word isn't clipped.
- **Quiet gap after TTS.** 300 ms pause between `afplay` returning and the
  mic starting to listen, so we don't capture our own tail.
- **Conversation memory.** Rolling 8-turn context is passed to the LLM so the
  assistant remembers what you said 2 turns ago.
- **Retry with backoff.** STT, TTS, and chat calls retry 3 times with
  exponential backoff on transient 5xx / network errors.
- **Substring exit detection.** "ok thanks bye", "shut down please",
  "that's all thanks" — any of those will end the session.
- **Clean shutdown.** `Ctrl+C` closes the mic stream and the audio device
  properly. Top-level `try/except` announces fatal errors via TTS.

---

## Requirements

- **macOS** (tested) or Linux/Windows (audio playback falls back to `aplay` /
  `paplay` / `ffplay`)
- **Python 3.10+**
- A working microphone
- A Sarvam AI API key from [dashboard.sarvam.ai](https://dashboard.sarvam.ai)

System dependency: `ffmpeg` is no longer needed (we removed local Whisper).

### Plivo for telephony

If you want the assistant on a real phone number:
- A **Plivo** account with an active number

Install telephony dependencies:

```bash
pip install fastapi "uvicorn[standard]"
```

**Running with Plivo (requires a public URL for Plivo to reach your server):**

```bash
# Terminal 1 — keep this running all day
ngrok http 5000

# Terminal 2 — start the server with the ngrok URL
PLIVO_PUBLIC_BASE_URL=https://abc123.ngrok.io uvicorn app.main:app --reload
```

Then configure your Plivo number's Answer URL in the Plivo console to point to:
`https://abc123.ngrok.io/call/incoming`

---

## Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Create your .env from the template and fill in your key
cp .env.example .env
# then edit .env and replace YOUR_SARVAM_API_KEY_HERE with your real key
```

### Running it

**Local mic (CLI):**

```bash
python3 -m app.cli
```

**Telephony server (FastAPI):**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

Say something when you see `[listening] ...`. Say "goodbye" (or anything
containing "exit", "quit", "stop", "bye", "shut down", "that's all", etc.)
to end the session.  `Ctrl+C` also works.

---

## Configuration

All tuning lives in `.env` (see `.env.example` for every available variable):

| Env var | Default | What it controls |
|---|---|---|
| `SAMPLE_RATE` | 16000 | Mic sample rate (Hz). Must be 8k/16k/32k/48k for `webrtcvad`. |
| `VAD_AGGRESSIVENESS` | 3 | 0–3. Higher = stricter speech detection (better for noisy rooms). |
| `SILENCE_END_MS` | 400 | Trailing silence that ends a turn. Lower = snappier but may clip mid-thought pauses. |
| `MAX_UTTERANCE_MS` | 60000 | Hard cap per utterance (safety net). |
| `PRE_SPEECH_MS` | 200 | Audio kept before the first voiced frame, prevents first-word clipping. |
| `MIN_SPEECH_MS` | 250 | Minimum speech duration to be considered a real utterance. |
| `MAX_HISTORY_TURNS` | 8 | Rolling context window (in turns). |
| `RETRY_ATTEMPTS` | 3 | HTTP retries on transient errors. |
| `SARVAM_STT_MODEL` | `saaras:v3` | Saaras model to use. |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | Bulbul model to use. |
| `SARVAM_LANGUAGE_CODE` | `en-IN` | BCP-47 code for both STT and TTS. |
| `SARVAM_CHAT_MODEL` | `sarvam-105b` | LLM model name. |
| `SYSTEM_PROMPT` | *(see .env)* | Instructions to the LLM. Keep short for phone deployments. |

### Switching languages

To make the assistant Hindi/Hinglish, change the language codes at the top:

```python
STT_LANGUAGE = "hi-IN"  # or "bn-IN", "ta-IN", etc.
TTS_LANGUAGE = "hi-IN"
TTS_SPEAKER = "priya"    # any Bulbul v3 voice
```

Saaras supports 23 languages (22 Indian + English). Bulbul supports 11.
Sarvam-105B is fine with any of them.

---

## Cost

At Sarvam's published rates (verified against
[the pricing page](https://docs.sarvam.ai/api/getting-started/pricing)):

| Endpoint | Rate |
|---|---|
| Saaras v3 STT | ₹30/hour of audio → **₹0.50/min** of speech |
| Bulbul v3 TTS | ₹30 / 10K characters → **₹0.003/char** |
| Sarvam-105B chat | ₹29.28 / 1M input tokens, ₹73.20 / 1M output tokens |

**Per minute of typical conversation** (≈8 turns, ≈64 s of user speech, ≈30
words of model reply each):

| Component | Per minute |
|---|---|
| STT | ₹0.533 |
| TTS | ~₹0.012 |
| LLM | ~₹0.00004 (essentially noise) |
| **Total** | **≈ ₹0.55/min** |

STT is ~98% of the bill. The LLM cost is negligible for voice workloads.

The first ₹100 of API usage is on Sarvam — enough for ~3 hours of
conversation at typical traffic.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'requests'`** — your `python3` resolves
to macOS's system Python, which has no third-party packages. Either run the
script with the python.org framework install (`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`),
or prepend it to your `PATH` in `~/.zshrc`:

```bash
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
```

**Cursor's "Run File" button still uses `/usr/bin/python3`** — add a
`code-runner.executorMap` entry to your Cursor user settings
(`~/Library/Application Support/Cursor/User/settings.json`):

```json
"code-runner.executorMap": {
    "python": "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
}
```

**The assistant keeps cutting off mid-sentence** — raise `SILENCE_END_MS` to
500 or 600. Lower values are snappier but less forgiving of mid-thought
pauses.

**The assistant feels slow to start listening after TTS** — lower
`POST_TTS_QUIET_GAP` to 0.15. If you start catching the tail of your own TTS
in the next transcript, raise it back.

**No audio device found** — check System Settings → Privacy & Security →
Microphone, and make sure your terminal/Python has permission.

**`SARVAM_API_KEY is missing`** — `.env` doesn't exist or still has the
placeholder. Copy from `.env.example` and fill in your real key.

---

## Project layout

```
Voice-AI/
├── app/
│   ├── main.py                 # FastAPI app entry point
│   ├── config/                 # env var loading
│   │   ├── settings.py        # voice / pipeline settings
│   │   ├── sarvam.py         # Sarvam credential builder
│   │   └── plivo.py          # Plivo credential builder
│   ├── core/                  # pure-stdlib utilities
│   │   ├── http.py           # retry+backoff POST
│   │   ├── audio_io.py       # PCM → WAV container
│   │   └── text.py           # markdown stripper
│   ├── models/               # Pydantic schemas & data shapes
│   │   ├── inbound.py        # InboundSchema (Plivo webhook)
│   │   ├── hangup.py         # HangupSchema (Plivo webhook)
│   │   ├── outbound.py        # OutboundCallRequest / OutboundCallResponse
│   │   ├── plivo.py          # PlivoCallRequest (Plivo API)
│   │   ├── telephony.py       # CallContext (WebSocket metadata)
│   │   ├── audio.py          # Utterance
│   │   ├── transcript.py      # Transcript
│   │   ├── messages.py       # Message (LLM turn)
│   │   └── credentials.py     # SarvamCredentials / PlivoCredentials
│   ├── services/             # external I/O (one class/func per integration)
│   │   ├── sarvam_stt.py     # Saaras v3 transcription
│   │   ├── sarvam_chat.py    # Sarvam-105B chat
│   │   └── plivo_client.py   # Plivo outbound call API
│   ├── agents/               # business-logic actors
│   │   └── reasoner.py       # ConversationHistory + LLM call
│   ├── controllers/          # business logic, orchestrate services
│   │   ├── inbound.py        # InboundController
│   │   ├── hangup.py        # HangupController
│   │   ├── outbound.py       # OutboundController
│   │   └── telephony_controller.py  # Plivo WebSocket voice loop
│   └── routers/              # FastAPI APIRouter instances
│       ├── plivo_webhook.py  # /call/incoming · /call/hangup · /call/outbound
│       └── telephony.py      # /stream (WebSocket) · /health
├── requirements.txt     # Python dependencies
├── .env.example         # template for .env (committed)
├── .env                 # your real keys (gitignored)
└── .vscode/
    └── settings.json    # pins Cursor to the framework Python
```

### Running it

```bash
python3 "Voice AI.py"
```

or equivalently via the package:

```bash
python3 -m app
```
