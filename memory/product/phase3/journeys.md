# Phase 3 journeys

- JRN-29 — steps: in a rehearsal, edit the current line's text and save; reload the script page. — expected: new text shown in rehearsal and in the Guião editor after reload; listening resumes after save.
- JRN-30 — steps: in a rehearsal, change a line's character from EDDIE to GARY. — expected: line now shows under GARY; if GARY is the AI, it is spoken in GARY's voice; persists after reload; blocks recomputed (if it became the actor's line, it's listened to).
- JRN-31 — steps: in a rehearsal, mark a line "Cortada". — expected: line shown struck through; rehearsal passes over it (not spoken, not judged); persists in editor.
- JRN-32 — steps: simulate a failed save (backend error). — expected: "Não foi possível guardar a alteração"; old line kept.
- JRN-33 — steps: click a line far ahead, choose "Saltar para aqui". — expected: rehearsal continues from that line within 1 s.
- JRN-34 — steps: turn on "Modo Saltar" before starting. — expected: only the cue line immediately before each of the actor's blocks is played; other AI lines skipped.
- JRN-35 — steps: start without Modo Saltar, turn it on mid-rehearsal (button or S key), then off. — expected: takes effect from the next line each time.
- JRN-36 — steps: view a script with 3 consecutive lines of one character. — expected: grouped under one name header.
- JRN-37 — steps: reach a line > 1000 characters. — expected: shown in a fixed-height window that reveals progressively; nav buttons don't move (same position as on a short line).
- JRN-38 — steps: use →, ←, Space, Enter, H, E, S, T during a rehearsal; press ? — expected: each does its action; "?" shows the shortcut list; typing in the edit/text fields doesn't trigger shortcuts.
- JRN-39 — steps: in the Guião editor, set a page-number line to "Texto não pertencente" and a line to "Cortada"; bulk-select 3 lines and set them to "Rubrica". — expected: saved; "texto não pertencente" doesn't appear in rehearsal; "Cortada" appears struck through and is skipped; the 3 lines become directions.
- JRN-40 — steps: import a new script (paste). — expected: character detection works as before (regression).
- JRN-41 — steps: run a normal rehearsal of "A Espera". — expected: Phase 2 behaviour intact (engine label, blocks, voices, summary).
