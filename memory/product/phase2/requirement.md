# Phase 2 — Listening & judging engine + free voices (phase-2)

Goal: the app hears the actor faithfully on a laptop mic with speakers, judges with script-aware reasoning, treats consecutive actor lines as one block, replies with no perceived latency, and costs nothing (Deepgram free credit, Gemini free tier, free Edge pt-PT voices). See ../overview.md (F-11..F-16, Integrations).

## Functional requirements
- REQ-28 [always] The system shall use Deepgram streaming STT (Portuguese) as the primary listening engine.
- REQ-29 [always] The system shall issue the browser a short-lived Deepgram credential from the backend, never the raw key.
- REQ-30 [unwanted] If Deepgram fails to connect, then the system shall switch to Gemini Live transcription without losing words already captured in the current block.
- REQ-31 [unwanted] If Gemini Live also fails, then the system shall switch to the browser Web Speech engine.
- REQ-32 [event] When the engine changes, the system shall show the active engine name in the rehearsal screen ("Escuta: Deepgram" / "Escuta: Gemini" / "Escuta do browser").
- REQ-33 [unwanted] If a key is missing (e.g. running locally), then the system shall show "Falta a chave <motor> no ficheiro backend/.env" and use the next engine.
- REQ-34 [always] The system shall send the expected words of the current block as recognition hints (keyterms / vocabulary) to the engine (interpreted).
- REQ-35 [always] The system shall align what was heard to the expected text with phonetic pt-PT similarity, so a word that sounds like the expected word counts as the expected word.
- REQ-36 [always] The system shall count a difference as an error only when it changes meaning or wording beyond recognition distortion (interpreted).
- REQ-37 [event] When a block ends with doubtful differences, the system shall confirm them in the background (LLM, Emergent key) without delaying the AI reply.
- REQ-38 [always] The final report shall list only differences confirmed as real.
- REQ-39 [always] The system shall treat consecutive lines of the actor's character, with no other character's line in between, as one block (interpreted: stage directions in between don't break the block).
- REQ-40 [state] While the actor is speaking a block, the system shall keep listening through pauses without judging until the block's end words are heard or "Terminei" is tapped.
- REQ-41 [event] When a block ends, the system shall clear the transcript so the next block starts empty.
- REQ-42 [unwanted] If text from the previous block reappears in the new transcript, then the system shall ignore it.
- REQ-43 [event] When the actor's block ends, the system shall start the next AI line immediately (local verdict first).
- REQ-44 [always] The system shall keep the existing hint-on-silence and strictness levels (grave / rigor / nunca) working per block.
- REQ-45 [always] The system shall voice AI characters with free Microsoft Edge pt-PT neural voices by default, each character distinct (voice + pitch/rate).
- REQ-46 [unwanted] If Edge TTS fails, then the system shall use OpenAI TTS via the Emergent key (logged "TTS FALLBACK").
- REQ-47 [optional] Where a character has an ElevenLabs voice set and a key exists, the system shall use ElevenLabs for that character.
- REQ-48 [always] The system shall keep ignoring the AI's own voice coming from the speakers.
- REQ-49 [always] The backend shall serve its API spec at /api/openapi.json.

## Quality requirements
```
Q-28  Tag: Listening.Accuracy
      Scale: % of correctly said words judged correct (laptop mic + speakers, demo script read correctly)
      Meter: human, 3 full read-throughs of "A Espera"
      Must: 95%   Plan: 99%
Q-29  Tag: Report.FalseErrors
      Scale: false errors in final report after a fully correct read-through
      Meter: human + automated with recorded/synthesised correct audio
      Must: ≤2   Plan: 0
Q-30  Tag: Flow.Latency
      Scale: ms from actor's block end detected → AI audio starts
      Meter: window.__ensaioLatency, 10 turns
      Must: ≤700 ms   Plan: ≤350 ms
Q-31  Tag: Listening.TranscriptDelay
      Scale: ms from word spoken → word shown live
      Meter: human / console timings
      Must: ≤800 ms   Plan: ≤300 ms
Q-32  Tag: Blocks.Accumulation
      Scale: blocks whose transcript contains words from a previous block
      Meter: automated + human, 10 consecutive blocks
      Must: 0   Plan: 0
Q-33  Tag: Voices.Quality
      Scale: characters with a Brazilian accent or two characters sharing an identical voice
      Meter: human
      Must: 0   Plan: 0
Q-34  Tag: Cost
      Scale: paid calls per rehearsal outside free tiers (Emergent LLM excluded)
      Meter: backend logs
      Must: 0   Plan: 0
Q-35  Tag: Resilience.Failover
      Scale: words lost when the engine switches mid-block
      Meter: automated (kill primary connection)
      Must: 0 rehearsal crash; ≤1 s of words lost   Plan: 0
```
