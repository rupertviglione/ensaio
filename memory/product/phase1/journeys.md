# Phase 1 journeys

- JRN-1 · steps: open demo "A Espera", start a rehearsal, listen to AI lines · expected: every AI line plays with an ElevenLabs pt-PT voice (backend reports provider "elevenlabs" and a voice from the pt-PT list); characters have distinct voices; no Brazilian voice IDs used.
- JRN-2 · steps: create a session · expected: audio for all AI lines is generated before/while the rehearsal starts; requesting an AI line's audio returns cached audio quickly (< 300 ms server time).
- JRN-3 · steps: create a script with an AI line of > 1500 characters, rehearse · expected: the full line plays, no truncation, no error, no voice change mid-line.
- JRN-4 · steps: start rehearsal, reach actor's turn · expected: backend issues a Scribe single-use token (endpoint works); the ElevenLabs key never appears in any frontend response/bundle.
- JRN-5 · steps: speak the line · expected: live transcript appears word by word; as soon as the last words are said, the AI's next line starts with no perceptible delay (human).
- JRN-6 · steps: speak half the line, stay silent 8 s, then finish · expected: the turn does not end during silence; after 5 s the prompter says and shows the next 2–4 words; finishing the line ends the turn normally, no error for the pause.
- JRN-7 · steps: stay silent after a hint · expected: another hint with the next words after another 5 s; turn still open.
- JRN-8 · steps: tap "Terminei" mid-line · expected: turn ends and is evaluated as today.
- JRN-9 · steps: set hint time to 10 s in session setup · expected: hints appear after 10 s; values outside 3–15 are rejected.
- JRN-10 · steps: start speaking right as the AI line ends (or slightly before) · expected: the first words are in the transcript (human).
- JRN-11 · steps: rehearse with speakers (no headphones) · expected: the AI voice is not counted as the actor's speech; turn not ended by the AI's own words (human).
- JRN-12 · steps: speak an actor line lasting > 90 s · expected: no error, no cut, full transcript, correct evaluation (human).
- JRN-13 · steps: say the line with a wrong word in "grave"/"rigor" modes · expected: same behaviour as today (interruption/notes per strictness).
- JRN-14 · steps: simulate ElevenLabs TTS failure · expected: line still plays via fallback; rehearsal does not break.
- JRN-15 · steps: existing flows (library, new script, upload, summary) · expected: still work (regression).
