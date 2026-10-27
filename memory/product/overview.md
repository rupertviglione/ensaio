# Requirements: Ensaio (Round 5 — vozes pt-PT, tempo real, pausas)

Existing app (React web /app/frontend + FastAPI /app/backend/server.py + MongoDB). See /app/memory/PRD.md for history (Rounds 1–4). This round improves the rehearsal engine.

## Core Value
An actor rehearses a script out loud with AI scene partners that sound like natural European-Portuguese actors, reply instantly, and never cut off or misjudge the actor.

## Personas & Roles
- Actor (single user, no login): rehearses their character's lines out loud, with headphones or with speakers.

## Features
| id | feature | persona | phase |
|---|---|---|---|
| F-1 | AI characters speak with natural, native European-Portuguese (pt-PT) ElevenLabs voices — never Brazilian | Actor | 1 |
| F-2 | Real-time listening of the actor via ElevenLabs Scribe v2 Realtime (streaming, word by word) | Actor | 1 |
| F-3 | Actor's line ends by content (last words said) or by tap — never by a short silence | Actor | 1 |
| F-4 | After X seconds of silence mid-line, the prompter gives a hint (next missing words) instead of judging an error | Actor | 1 |
| F-5 | Mic stays always open; the start of the actor's line is never lost after the AI finishes | Actor | 1 |
| F-6 | AI partner replies with near-zero latency after the actor's line ends (pre-generated audio, local match first) | Actor | 1 |
| F-7 | Long lines (actor and AI) work without errors, timeouts or truncation | Actor | 1 |
| F-8 | Works with headphones and with speakers (AI voice not mistaken for the actor) | Actor | 1 |
| F-9 | Error handling kept as today (strictness levels grave / rigor / nunca) | Actor | 1 |
| F-10 | Technical hardening: split server.py, remove tts_cache from git + eviction, single completion path, cached prompter audio, timeouts on LLM calls, cleanup dead code | — | 2 |

## Phases
- Phase 1 → Rehearsal engine: pt-PT voices, real-time listening, content-based end of line, hints on pauses, always-open mic, long lines → F-1..F-9. [requirement](phase1/requirement.md) · [journeys](phase1/journeys.md)
- Phase 2 → Technical hardening & cleanup → F-10.

## UI/UX Rules
- Keep the existing UI and Portuguese (pt-PT) copy; only add what's needed (hint display, silence-hint setting, "Terminei" tap stays).
- No visible waiting between the AI line and the actor's turn.

## Integrations
- ElevenLabs (user's own key, `ELEVENLABS_API_KEY` in backend/.env): TTS with native pt-PT voices (model: best natural multilingual model, e.g. eleven_multilingual_v2 / v3, `language_code` pt) and Scribe v2 Realtime STT (`scribe_v2_realtime`) via single-use tokens issued by backend (key never sent to browser).
- Emergent LLM key: Claude (existing parse/summary/turn evaluation) — unchanged.
- OpenAI TTS/STT: fallback only if ElevenLabs fails.

## Edge Cases
- Long silence while remembering → hint, not error, not end of line.
- Very long lines (> 1 min speaking, > 1000 characters).
- Speakers: AI voice leaks into mic.
- Actor starts speaking slightly before the AI ends.
- ElevenLabs token/connection drops mid-line → reconnect without losing the line.
- Key missing permissions → clear message, fallback.

## Seed Data
- Existing demo script "A Espera" stays.
