# Voice Agent Worker — Milestones (M1 → M3)

**Owner scope:** Voice Agent Worker only (Python realtime loop).  
**Branch:** `feat/voiceagentM1`  
**Architecture:** see `[ARCHITECTURE.md](./ARCHITECTURE.md)`  
**Not in scope for these milestones:** Voice Orchestrator implementation, Chatwoot wiring, OTP/account APIs, SIP/telephony trunks, UAE region, human transfer, callbacks, Langfuse production, ML classifiers.

> **One-line goal.** Build the realtime phone/browser voice loop that hears the caller, talks back, and (later) *requests* tools through an orchestrator — without becoming a new support platform.

---



## Mental model (worker only)

```text
Caller audio (browser first → SIP later)
        ↓
   LIVEKIT room
        ↓
┌───────────────────────────────┐
│     VOICE AGENT WORKER        │  ← you own this
│                               │
│  Audio → STT → Claude → TTS   │
│  (+ call state, tools later)  │
└───────────────┬───────────────┘
                │ HTTP (later)
                ▼
      Voice Orchestrator API     ← other owners / later milestones
```

**Hard rules for all milestones**

- No direct DB writes (tickets, FAQ, users).
- No investment advice / orders / transfers / withdrawals / MPIN.
- Caller ID is not auth (OTP comes after M3 in product plan — not here).
- Prefer thin worker + mocked orchestrator until real APIs exist.

---



## Milestone overview


| Milestone                                    | Theme                      | Exit criteria (worker)                                                          |
| -------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| **[M1](#m1--basic-voice-loop)**              | Hear → think → speak       | 20+ internal test sessions; greeting + FAQ-style reply in EN (Hinglish stretch) |
| **[M2](#m2--call-state--language--kb-tool)** | Stateful call + first tool | Language state + KB search via orchestrator client (mock OK)                    |
| **[M3](#m3--policy-skeleton--reliability)**  | Safe + reliable loop       | Deterministic state machine + timeouts/fallbacks + tool budget                  |


Later product work (OTP, tickets, SIP India number, human handoff, callbacks) sits **after M3** and mostly needs orchestrator + infra — track separately.

---



## M1 — Basic voice loop

**Why first:** Prove realtime audio works before any backend integration.

### Build

1. Python worker process that joins a LiveKit room as an agent.
2. Audio pipeline (minimal):
  - VAD
  - LiveKit turn detector (not fixed 500ms silence alone)
  - Streaming STT (Sarvam primary; Deepgram stub/fallback interface OK)
3. LLM: Claude — short support-style system prompt (no tools yet).
4. Streaming TTS (Sarvam Bulbul) → play back into the room.
5. Local / browser call path (no SIP required for M1).
6. Config via env (LiveKit URL, keys, STT/TTS/LLM keys) — document in `.env.example` when added.
7. Structured logs per turn: `call_id`, `turn_id`, STT/LLM/TTS latency (console/logger is enough; Langfuse later).



### Explicitly out of M1

- SIP / Exotel / Plivo
- Orchestrator / KB / tickets / OTP
- Region matrix (India vs UAE)
- Human transfer, callbacks, recordings to S3
- Custom ML intent/risk models



### Done when

- [ ] Worker joins room and greets: “Hello, how can I help you?”
- [ ] User speaks → STT → Claude → TTS → user hears reply
- [ ] Barge-in / interruption does not crash the worker
- [ ] Provider interfaces exist (`STTProvider`, `TTSProvider`) so Sarvam↔Deepgram can swap later
- [ ] **≥ 20 internal test calls/sessions** documented (browser OK)
- [ ] README section: how to run locally (room create → join → talk)



### Suggested package layout (M1)

```text
apps/ai_agents/src/app/agents/voice_support/
├── ARCHITECTURE.md
├── README.md                 ← this file
└── worker/                   ← implement in M1
    ├── __init__.py
    ├── main.py               # entrypoint
    ├── session.py            # one call / room session
    ├── audio/                # VAD, turn, barge-in hooks
    ├── providers/
    │   ├── stt.py
    │   ├── tts.py
    │   └── llm.py
    └── config.py
```

Exact filenames can flex; keep the five layers from `ARCHITECTURE.md` readable.

---



## M2 — Call state + language + KB tool

**Why next:** Turn the demo into a support-shaped agent without building a second FAQ DB.

### Build

1. **Call state** on the worker session:
  - `CALL_STARTED` → `GREETING` → `LISTENING` → `UNDERSTANDING` → `RESPONSE` → `LISTENING`
  - Region flag: `region = india` (config only; UAE later)
2. **Language state**
  - Detect EN / HI / Hinglish from STT (provider signal OK)
  - Allow mid-call switch (“Actually Hindi mein batao”)
  - Do **not** switch language on a single English word (multi-turn confidence)
3. **First tool — KB only**
  - Worker tool: `search_support_kb(query)`
  - Implementation: HTTP client to Voice Orchestrator (or a **local mock** returning FAQ snippets)
  - Claude may call the tool; worker must not hit PgVector/DB directly
4. Guardrail prompt: refuse investment advice; offer to connect to team (text-only for now).
5. Latency budget awareness: stream LLM → TTS; measure p50/p95 toward < 1.2s / < 2.0s (stretch; log first).



### Explicitly out of M2

- Real ticket create/status
- OTP / verified token
- Live Chatwoot
- SIP India DID



### Done when

- [ ] Session keeps call + language state across turns
- [ ] Hinglish utterance gets a coherent reply (quality imperfect OK)
- [ ] KB tool path works end-to-end with mock **or** real orchestrator
- [ ] Advice questions are refused without crashing the loop
- [ ] Unit/integration tests for: language switch, KB tool request shape, advice refusal

---



## M3 — Policy skeleton + reliability

**Why next:** Make the worker production-safe enough to hang real tools on later.

### Build

1. **Policy gate before tools** (even with only KB):
  ```text
   Claude proposes tool → Policy → allow/deny → Tool Gateway → Orchestrator client
  ```
2. Expand state machine exits (stubs OK):
  - `POLICY_BLOCK`, `AUTH_REQUIRED` (stub: “I need to verify you” — no real OTP yet)
  - `CALL_END`
3. **Reliability**
  - Timeouts per STT / LLM / TTS / orchestrator call
  - STT fallback interface wired (Sarvam fail → Deepgram if configured)
  - Circuit breaker skeleton (CLOSED / OPEN / HALF_OPEN) for STT + LLM
  - Tool call budget per turn/call (e.g. max 4)
4. **Idempotency keys** on write-shaped tool requests (even if only mock writes):
  - `idempotency_key = call_id + tool_name + request_hash`
5. **Output path**: response validator stubs (PII/advice) before TTS — rules OK.
6. Selective preemption: FAQ-ish intents may stream early; “account” intents wait for final STT (heuristic/rules).



### Explicitly out of M3

- Shipping OTP/ticket/human-transfer product features (those need orchestrator + infra owners)
- Custom intent/risk ML models
- Production Langfuse dashboards (optional: emit Langfuse traces if keys exist)



### Done when

- [ ] No tool runs without passing the policy gate
- [ ] Provider timeout → fallback or graceful “please repeat” path
- [ ] Tool budget enforced; no infinite tool loops
- [ ] Idempotency key always set on mutating tool request payloads
- [ ] Docs updated: how to run M1–M3 locally + what “done” means for PR review

---



## After M3 (not this README’s commitment)


| Later                            | Depends on                           |
| -------------------------------- | ------------------------------------ |
| India SIP number + Exotel/Plivo  | Telephony + LiveKit SIP              |
| Real FAQ via existing support KB | Orchestrator + `customer_support` KB |
| Tickets / Chatwoot               | Orchestrator + ticket APIs           |
| OTP + read-only account token    | Orchestrator + auth APIs             |
| Callback (BullMQ)                | Redis job infra                      |
| Human transfer same LiveKit room | Chatwoot availability + agent client |
| Langfuse evals + S3 recordings   | Infra + retention policy             |
| UAE region                       | Same worker, different config        |


---



## Clean production architecture

```text
                         ┌──────────────────────┐
                         │       CUSTOMER       │
                         │   Phone / Mobile     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ TELEPHONY / SIP      │
                         │ India: Exotel/Plivo  │
                         │ UAE: Licensed CPaaS  │
                         └──────────┬───────────┘
                                    │ SIP
                                    ▼
                         ┌──────────────────────┐
                         │      LIVEKIT         │
                         │ SIP + Room + Media   │
                         └──────────┬───────────┘
                                    │
                                    ▼
              ╔══════════════════════════════════════════╗
              ║          VOICE AGENT WORKER              ║
              ║                Python                    ║
              ║                                          ║
              ║  1. AUDIO PIPELINE                       ║
              ║     Noise → VAD → Turn Detector          ║
              ║     → Barge-in → Streaming STT           ║
              ║     → Language Detection                 ║
              ║                     │                    ║
              ║  2. CONVERSATION / AGENT CORE            ║
              ║     Intent → Risk → Context → Claude     ║
              ║     Planning → Next Action               ║
              ║                     │                    ║
              ║  3. POLICY + AUTHORIZATION              ║
              ║     Region / Auth / PII / Advice         ║
              ║     Tool permissions / State machine     ║
              ║                     │                    ║
              ║  4. TOOL GATEWAY                         ║
              ║     FAQ | Ticket | OTP | Callback        ║
              ║     Agent Availability | Transfer        ║
              ╚═════════════════════╪════════════════════╝
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │    VOICE ORCHESTRATOR API    │
                    │        Existing Backend      │
                    └──────────────┬───────────────┘
                                   │
               ┌───────────────────┼────────────────────┐
               │                   │                    │
               ▼                   ▼                    ▼
       ┌──────────────┐    ┌───────────────┐    ┌───────────────┐
       │   CHATWOOT   │    │ EXISTING AI KB│    │ EXISTING APIs │
       │ Conversations│    │ FAQ / RAG     │    │ OTP           │
       │ Tickets      │    │ support_kb    │    │ Account       │
       │ Teams        │    │ vectors       │    │ KYC           │
       │ Human agents │    │               │    │ Ticket APIs   │
       └──────┬───────┘    └───────────────┘    └───────────────┘
              │
              ▼
        HUMAN AGENT
        Same LiveKit call
```

