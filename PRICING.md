# Cost Breakdown — Sarvam Voice AI Pipeline

Last verified against [Sarvam's pricing page](https://docs.sarvam.ai/api/getting-started/pricing).

## Unit rates

| Endpoint | Model | Billing unit | Rate |
|---|---|---|---|
| STT | `saaras:v3` | per second of audio | **₹30/hour** (≈ ₹0.00833/s) |
| TTS | `bulbul:v3` | per character | **₹30 / 10,000 characters** (≈ ₹0.003/char) |
| Chat | `sarvam-105b` | per 1M tokens | **₹29.28 input** / **₹73.20 output** |

## What this pipeline actually uses per minute

The pipeline makes three Sarvam API calls per turn:

1. `POST /speech-to-text` — billed on seconds of audio uploaded
2. `POST /v1/chat/completions` — billed on tokens in (prompt + history) and tokens out (reply)
3. `POST /text-to-speech` — billed on characters of text sent

A "turn" is roughly: you speak → assistant transcribes → assistant reasons → assistant speaks.

### Reference profile (medium conversation)

| Quantity | Per minute |
|---|---|
| Turns | ~8 |
| User speech captured by VAD | ~64 s |
| Average user utterance | ~8 s |
| Tokens in per turn (system prompt + 8-turn history + user text) | ~80 |
| Tokens out per turn (model reply, capped at 128) | ~40 |
| TTS characters per turn (≈30 words × 5 chars) | ~150 |

### Per-minute cost — medium profile

| Component | Per minute | Calc |
|---|---|---|
| **STT** (Saaras v3) | **₹0.533** | 64 s × (₹30 / 3600 s) |
| **TTS** (Bulbul v3) | **₹0.012** | 1200 chars × (₹30 / 10,000 chars) |
| **Chat input** (Sarvam-105B) | **₹0.000019** | 640 tokens × (₹29.28 / 1,000,000) |
| **Chat output** (Sarvam-105B) | **₹0.000023** | 320 tokens × (₹73.20 / 1,000,000) |
| **Total** | **≈ ₹0.545/min** | |

LLM cost is essentially noise — about **₹0.04 per 1,000 minutes** of talking. STT dominates at ~98% of the bill.

## Three usage profiles

| Profile | Turns/min | Speech/min | TTS chars/min | Tokens in/out per min | Cost/min | Cost/hour |
|---|---|---|---|---|---|---|
| Light Q&A (short replies like "yes"/"no") | 5 | ~25 s | 600 | 400 / 160 | **₹0.21** | **₹12.6** |
| Medium conversation (default) | 8 | ~64 s | 1,200 | 640 / 320 | **₹0.54** | **₹32.7** |
| Heavy monologue (long replies, long turns) | 15 | ~180 s | 3,500 | 1,800 / 900 | **₹1.55** | **₹92.8** |

## Hourly / daily / monthly projections (medium profile)

| Horizon | Cost (₹) | Cost (USD, ~₹83.5/$) |
|---|---|---|
| 1 hour of talking | ~₹33 | ~$0.40 |
| 1 hour/day × 30 days | ~₹980 | ~$11.70 |
| 4 hours/day × 30 days | ~₹3,920 | ~$46.95 |

## Free credits

Every new Sarvam account comes with **₹100 of free credits**. At medium
traffic that's roughly **3 hours of talking** before any payment is needed.

## Cost levers

If you need to lower the bill:

1. **STT is the lever, not the LLM.** 98% of the cost is transcription. The
   pipeline already avoids empty transcripts (VAD-gated) and short utterance
   billing (rounds up to whole seconds per request, so the 300 ms pre-roll is
   not billed as a separate request).
2. **Lower `MAX_NEW_TOKENS`.** Setting it from 128 to 64 cuts the LLM output
   bill in half — but the LLM is ~0.004% of total cost, so this saves almost
   nothing in practice.
3. **Switch Bulbul v3 → v2.** Halves TTS cost (₹15/10K instead of ₹30/10K),
   but voice quality drops noticeably. v3 is recommended.
4. **Lower the conversation history (`MAX_HISTORY_TURNS`).** Saves a small
   amount of input tokens on each LLM call. Again — marginal.

The honest answer is that voice assistants on Sarvam are very cheap
(₹30–90/hour of actual talking) and the cost is dominated by whichever
component you can't avoid: transcribing what the user said.

## Adding telephony (phone-call deployment)

If you expose the same pipeline over a phone number using Sarvam's
[Voice Agents platform](https://indus.sarvam.ai/samvaad) or a bring-your-own
provider (Twilio, Exotel, Smartflo, Pulse, Intalk, Vobiz), the model rates
above stay identical — but two extra layers get added to the bill.

### Layer 1 — Telephony provider per-minute charges

This is **separate from Sarvam's pricing** and is billed by the telephony
provider (or by Sarvam if you rent a number from them). Sarvam's own docs
explicitly do **not** publish a per-minute call rate — they refer you to
the dashboard or to their team for current numbers.

**Number rental (Sarvam)** — billed from your Sarvam wallet, minimum 30-day
rental with auto-renewal. Exact price per number is shown in the number
catalog in the Sarvam dashboard (varies by number/region).

**Per-minute voice charges** — these come from the underlying provider you
connect to, not from Sarvam:

| Provider | Approx. per-minute voice (India) | Notes |
|---|---|---|
| Twilio | ₹1–3/min (mobile) | Check twilio.com/voice/pricing for current rates; international varies widely |
| Exotel | ~₹1/min | India-focused; check exotel.com/pricing |
| Smartflo (Tata Tele) | ~₹0.80–1/min | India-focused; check smartflo.tatateleservices.com |
| Pulse, Intalk, Vobiz | not surveyed here | Check each provider's pricing page |

> **Caveat:** the per-minute numbers above are ballpark figures from
> providers' public pricing pages at the time of writing, not from Sarvam's
> docs. Always verify against the provider's current pricing before
> budgeting. International and toll-free rates can be 5–10× higher than
> India-domestic mobile rates.

### Layer 2 — Sarvam model usage stays the same

The three model rates (STT, TTS, LLM) from the table at the top of this
document apply identically to phone calls — Sarvam doesn't charge more for
phone-channel STT than mic-channel STT. **For a one-hour phone call at
medium conversation density, expect the same ~₹33 of Sarvam model cost** as
for an hour of desktop mic usage.

### Combined cost — phone-call deployment

| Profile | Sarvam models | Telephony (Twilio India, mobile, mixed) | Total per hour |
|---|---|---|---|
| Light (5 short turns/min) | ~₹13 | ~₹80–180 | **~₹93–193** |
| Medium (8 turns/min) | ~₹33 | ~₹80–180 | **~₹113–213** |
| Heavy (15 long turns/min) | ~₹93 | ~₹80–180 | **~₹173–273** |

The Sarvam models are now **15–30%** of the total bill instead of 100%. The
telephony provider's per-minute charge dominates.

### Things that change technically when going phone

These don't change cost but do change the pipeline shape:

- **Audio format:** Twilio streams **8 kHz mono** (telephony-grade), not the
  16 kHz our VAD expects. Pipecat (or your framework of choice) resamples for
  you. If you wire STT directly, set `SAMPLE_RATE = 8000`.
- **Streaming STT instead of batched:** For real-time phone conversations you
  want `saaras:v3-realtime` over WebSocket (interim partial transcripts so
  the model can interrupt the user mid-sentence — "barge-in"). Pricing is
  the same ₹30/hour; billing is still per-second of audio.
- **Mic + afplay are replaced** by the provider's WebSocket media stream.
  No more `PyAudio` or `afplay` cost — but also no more control over local
  audio devices.

### Cost levers for phone deployments

1. **Pick a cheap telephony provider.** This is now the dominant cost.
   Sarvam-rented numbers or Indian providers (Smartflo, Exotel) are
   typically cheaper than Twilio for India-to-India.
2. **Use `saaras:v3-realtime` instead of batched STT.** Same price, but you
   get barge-in for free, which shortens calls (when users interrupt, you
   don't finish an irrelevant reply) — that lowers both model and telephony
   minutes.
3. **Cap max call duration** at the agent level (e.g. 5 minutes) to bound
   telephony minutes per call.
4. **Lower `MAX_NEW_TOKENS`** — still ~0.004% of total, so practically
   irrelevant.

## What doesn't show up in the bill (desktop pipeline)

These only apply to the desktop pipeline in `Voice AI.py`. The phone-call
version replaces all of these with the telephony provider's media stream:

- The VAD pipeline uses `webrtcvad`, which runs locally on-device — no API
  cost.
- Microphone capture uses `PyAudio`, local-only — no API cost.
- Audio playback uses macOS `afplay`, local-only — no API cost.

The only metered calls are the three Sarvam API calls per turn.

## Rate limits (Starter plan)

Sarvam's Starter plan allows **60 requests/minute** across all APIs. At
medium traffic (~24 requests/min: 8 turns × 3 calls), you have comfortable
headroom. Pro bumps this to 200/min; Business to 1,000/min.
