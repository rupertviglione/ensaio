# Phase 1 — Rehearsal engine (phase-1)

Goal: AI partners speak natural pt-PT, the actor is heard in real time, a line ends only when it's really finished, pauses get a hint (not an error), and the AI replies with no perceptible delay. Context: /app/memory/product/overview.md.

## Functional requirements
- REQ-1 [always] The system shall synthesise every AI character line with an ElevenLabs voice whose accent is European Portuguese (Portugal).
- REQ-2 [always] The system shall assign each AI character a distinct pt-PT voice from a curated list of at least 4 pt-PT voices (male and female).
- REQ-3 [always] The system shall use a native pt-PT ElevenLabs voice for the prompter.
- REQ-4 [unwanted] If ElevenLabs TTS fails for a line, then the system shall retry ElevenLabs once before falling back to OpenAI TTS (interpreted).
- REQ-5 [event] When a rehearsal session is created, the system shall pre-generate audio for all AI lines of the session.
- REQ-6 [always] The system shall synthesise AI lines of any length without truncating the text.
- REQ-7 [unwanted] If an AI line exceeds the provider's per-request limit, then the system shall split it at sentence boundaries and play the parts seamlessly (interpreted).
- REQ-8 [always] The system shall transcribe the actor's speech in real time with ElevenLabs Scribe v2 Realtime.
- REQ-9 [always] The system shall issue Scribe single-use tokens from the backend so the ElevenLabs key never reaches the browser.
- REQ-10 [while] While the actor is speaking, the system shall show the live transcript word by word.
- REQ-11 [event] When the live transcript contains the final words of the expected line, the system shall end the actor's turn.
- REQ-12 [event] When the actor taps "Terminei", the system shall end the actor's turn.
- REQ-13 [always] The system shall not end the actor's turn because of silence alone.
- REQ-14 [event] When the actor is silent mid-line for the configured hint time, the system shall give a hint with the next 2–4 missing words, spoken by the prompter and shown on screen.
- REQ-15 [always] The system shall default the hint time to 5 seconds, adjustable in session setup from 3 to 15 seconds (interpreted).
- REQ-16 [event] When a hint is given, the system shall keep listening and continue the same line from where the actor was.
- REQ-17 [unwanted] If the actor stays silent after a hint, then the system shall give the next hint after another hint interval.
- REQ-18 [always] The system shall keep the microphone stream open for the whole session.
- REQ-19 [event] When an AI line finishes playing, the system shall already be capturing the actor's audio (no gap).
- REQ-20 [event] When the actor starts speaking before the AI line fully ends, the system shall capture those first words.
- REQ-21 [while] While AI audio is playing, the system shall ignore transcript text that matches the AI line being played (speaker echo).
- REQ-22 [event] When the actor's turn ends with a clean local match, the system shall start the next AI line immediately without waiting for any server/LLM call.
- REQ-23 [always] The system shall run any LLM verification in parallel with playback of the next AI line, per today's strictness rules (grave / rigor / nunca).
- REQ-24 [always] The system shall transcribe actor lines of any length (at least 3 minutes) without error or cut.
- REQ-25 [unwanted] If the Scribe connection drops mid-line, then the system shall reconnect and keep the transcript already captured.
- REQ-26 [unwanted] If the ElevenLabs key lacks a needed permission, then the system shall show "Chave ElevenLabs sem permissão para <função>" and fall back to the previous engine.
- REQ-27 [always] The system shall keep today's error-handling and interruption behaviour by strictness level.

## Quality requirements
```
Q-1  Tag: Latency.ActorEndToAIStart
     Scale: ms from actor saying the last word to AI audio starting
     Meter: instrumented timestamps in rehearsal, 10 turns
     Must: ≤ 600 ms  Plan: ≤ 300 ms (estimate)
Q-2  Tag: Latency.AIEndToMicReady
     Scale: ms between AI audio end and actor audio being transcribed
     Meter: instrumented timestamps, 10 turns
     Must: 0 ms gap (capture already running)  Plan: 0 ms
Q-3  Tag: Voice.Accent
     Scale: % of lines a Portuguese listener judges as Portugal accent
     Meter: human, 20 lines
     Must: 100%  Plan: 100%
Q-4  Tag: Voice.Naturalness
     Scale: human rating 1–5
     Meter: human
     Must: ≥ 4  Plan: 5
Q-5  Tag: Reliability.LongLines
     Scale: errors/cuts per 10 long lines (> 60 s or > 1000 chars)
     Meter: automated (TTS) + human (speech)
     Must: 0  Plan: 0
Q-6  Tag: Accuracy.PrematureEnd
     Scale: turns ended before the actor finished, per 20 turns with 5–10 s pauses
     Meter: human
     Must: 0  Plan: 0
Q-7  Tag: Latency.STTPartial
     Scale: ms from word spoken to appearing on screen
     Meter: human/instrumented
     Must: ≤ 800 ms  Plan: ≤ 300 ms
```
