# Requirements: Ensaio (Round 6 — escuta fiel e grátis, blocos, edição e navegação no ensaio)

Existing app (React web /app/frontend + FastAPI /app/backend + MongoDB, no login, single actor). History in /app/memory/PRD.md (Rounds 1–5). Round 5 docs = phase1/. This round = phase2 + phase3.

## Core Value
Rehearsing with the app feels like rehearsing with a person: the actor speaks naturally, the AI partner understands faithfully (even with laptop mic + speakers), replies instantly, never flags errors that weren't made — all at zero cost for now.

## Personas & Roles
- Actor (single user, no login), desktop browser with laptop mic and speakers (also headphones); uses both the Emergent preview link and a local copy on their computer.

## Features
| id | feature | persona | phase |
|---|---|---|---|
| F-11 | Faithful real-time listening: Deepgram streaming STT (primary), Gemini Live (reserve), browser Web Speech (last resort), automatic failover | Actor | 2 |
| F-12 | Script-aware "reasoning" matching: what sounds like the expected text counts as the expected text (phonetic/fuzzy alignment, expected words as recognition hints) | Actor | 2 |
| F-13 | Final report counts only real errors (recognition distortions are discarded; differences confirmed before entering the report) | Actor | 2 |
| F-14 | Consecutive lines of the actor's character (and long speeches with pauses) are one block, validated only at the end; transcript cleared between blocks (no accumulation) | Actor | 2 |
| F-15 | Zero perceived latency: AI replies as soon as the actor's block ends; actor never waits for validation | Actor | 2 |
| F-16 | Free pt-PT voices for the AI characters (Microsoft Edge neural pt-PT voices), OpenAI via Emergent key as reserve; ElevenLabs optional (off by default, user doesn't want to spend) | Actor | 2 |
| F-17 | Edit a line during rehearsal: text, character attribution, mark as cut — saved permanently to the script | Actor | 3 |
| F-18 | Tap any line in the rehearsal text → jump the rehearsal there | Actor | 3 |
| F-19 | "Saltar" mode (toggle any time, also mid-rehearsal): skips stretches without the actor's character, playing only the cue line right before each actor line | Actor | 3 |
| F-20 | Display: consecutive lines of the same person grouped; long lines clipped in a fixed window and revealed progressively; nav buttons fixed in place | Actor | 3 |
| F-21 | Keyboard shortcuts for rehearsal controls (e.g. → next, ← previous, space pause), shown on screen | Actor | 3 |
| F-22 | Script editor after auto-parse: new kinds "texto não pertencente" (page numbers, headers — ignored in rehearsal) and "cortada" (struck through, skipped); fix character / direction / content | Actor | 3 |
| F-23 | Extra UX improvements proposed by the builder within the rehearsal flow (small, listed in the phase report) | Actor | 3 |

## Phases
- Phase 2 → Listening & judging engine + free voices → F-11..F-16. [requirement](phase2/requirement.md) · [journeys](phase2/journeys.md)
- Phase 3 → Rehearsal & script editing UX → F-17..F-23. [requirement](phase3/requirement.md) · [journeys](phase3/journeys.md)

## UI/UX Rules
- Keep the existing UI style and pt-PT copy.
- Rehearsal controls never move; text area scrolls/clips inside a fixed frame.
- Nothing blocks the actor's flow: no spinners between the actor's line and the AI reply.
- Keep the character detection / text preparation pipeline as is (user says it works well).

## Integrations
- Deepgram (user's own key, free $200 credit) — streaming STT, Portuguese (pt-PT), model nova-3 (or best Portuguese streaming model), keyterm prompting with expected words; browser gets a short-lived token from backend, key never sent to browser. Env `DEEPGRAM_API_KEY`.
- Google Gemini API (user's own free AI Studio key, new "AQ." format) — Gemini Live realtime transcription as reserve STT. Env `GEMINI_API_KEY`. Free tier limits apply.
- Browser Web Speech API — last resort STT.
- Microsoft Edge neural TTS (free, `edge-tts`): pt-PT voices (e.g. Raquel, Duarte, Fernanda) with pitch/rate variation to keep characters distinct — primary character + prompter voice.
- Emergent LLM key: Claude (parse, summary, background error confirmation) unchanged; OpenAI gpt-4o-mini-tts as TTS reserve.
- ElevenLabs: kept as optional per-character choice, off by default (no key now).

## Edge Cases
- Laptop speakers: AI voice leaking into mic must not count as the actor.
- ASR returns near-homophones / slight distortions of the correct words.
- Long speech with pauses, breaths, hint requests mid-block.
- Deepgram unavailable / out of credit / network drop → Gemini → Web Speech, without losing the current block.
- Gemini free-tier quota (429) → fall back cleanly.
- Running locally: env keys missing → clear message in pt-PT.

## Seed Data
- Existing demo script "A Espera" stays.
