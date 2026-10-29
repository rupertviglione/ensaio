# Phase 2 journeys

- JRN-16 — steps: open "A Espera", start a rehearsal, say your first line correctly into the laptop mic. — expected: rehearsal shows "Escuta: Deepgram"; words appear live as spoken; line accepted; AI reply starts with no visible wait.
- JRN-17 — steps: say a line correctly but where the recogniser hears a near-homophone (e.g. "à espera" heard as "há espera", "tás" for "estás"). — expected: line judged correct; no difference listed in the final report.
- JRN-18 — steps: read the whole demo script correctly, then finish. — expected: final report shows 0 (≤2) errors; score near 100.
- JRN-19 — steps: deliberately change a word that alters meaning (e.g. "nunca" → "sempre") or skip a sentence. — expected: flagged per strictness level; appears in the final report as a real difference.
- JRN-20 — steps: reach two or more consecutive lines of your character; say them as one speech with pauses between them. — expected: shown/handled as one block; no judgement until the end of the last line; no hint fired by a natural pause shorter than hint_seconds.
- JRN-21 — steps: after a block ends, the AI speaks, then say your next block. — expected: the live transcript starts empty; no words from the previous block appear.
- JRN-22 — steps: pause mid-block longer than hint_seconds. — expected: prompter gives the next 3 words and keeps listening (Round 5 behaviour kept) within the block.
- JRN-23 — steps: remove/invalidate the Deepgram key and start a rehearsal. — expected: "Falta a chave Deepgram…" or engine switches; screen shows "Escuta: Gemini"; rehearsal works.
- JRN-24 — steps: make Deepgram and Gemini both unavailable. — expected: "Escuta do browser"; rehearsal still works.
- JRN-25 — steps: drop the Deepgram connection mid-block. — expected: reconnect or failover; words already shown are kept; block completes.
- JRN-26 — steps: open the Vozes tab of a script and preview each character. — expected: each character has a distinct pt-PT (European) Edge voice; preview plays; no cost.
- JRN-27 — steps: rehearse with laptop speakers (no headphones). — expected: AI lines are not transcribed as the actor's speech; not judged.
- JRN-28 — steps: GET /api/openapi.json. — expected: 200 with the API spec.
