# Phase 3 — Rehearsal & script editing UX (phase-3)

Goal: during a rehearsal the actor can fix, cut or reassign any line, jump anywhere, skip stretches without their character, read comfortably (grouped lines, clipped long lines, fixed controls) and drive everything from the keyboard; the script editor gains "texto não pertencente" and "cortada". See ../overview.md (F-17..F-23). Builds on Phase 2 engine (blocks, Edge voices, Deepgram/Gemini) — keep it intact.

## Functional requirements
- REQ-50 [event] When the actor chooses "Editar" on a line in the rehearsal, the system shall open an inline editor for that line without stopping the session (interpreted: listening pauses while editing).
- REQ-51 [event] When the actor saves an edited text, the system shall save it permanently in the script.
- REQ-52 [event] When the actor changes the line's character, the system shall save the new attribution permanently in the script.
- REQ-53 [event] When the actor marks a line "Cortada", the system shall save it as cut permanently in the script.
- REQ-54 [always] The system shall show cut lines struck through.
- REQ-55 [always] The system shall skip cut lines in rehearsal (not spoken, not listened to, not judged).
- REQ-56 [event] When an edit changes who speaks or what's said, the system shall recompute blocks and audio for the remaining lines of the session (new TTS generated on the fly) (interpreted).
- REQ-57 [unwanted] If saving an edit fails, then the system shall show "Não foi possível guardar a alteração" and keep the previous line.
- REQ-58 [event] When the actor clicks a line in the rehearsal text, the system shall offer "Saltar para aqui".
- REQ-59 [event] When "Saltar para aqui" is chosen, the system shall continue the rehearsal from that line (no failure mode).
- REQ-60 [optional] Where "Modo Saltar" is on, the system shall play only the cue line immediately before each of the actor's blocks.
- REQ-61 [always] The system shall let "Modo Saltar" be toggled at any moment, including mid-rehearsal, taking effect from the next line.
- REQ-62 [always] The rehearsal text shall group consecutive lines of the same character under one name header.
- REQ-63 [always] The system shall show a long line inside a fixed-height window, revealing the rest progressively as it is spoken.
- REQ-64 [always] The navigation controls shall stay in a fixed position on screen regardless of line length.
- REQ-65 [always] The system shall support keyboard shortcuts: → next, ← previous, Space pause/resume, Enter "Terminei", H hint, E edit current line, S toggle Modo Saltar, T show/hide my text (interpreted).
- REQ-66 [always] The system shall show the shortcuts on screen (key hints on buttons + "?" overlay).
- REQ-67 [state] While typing in a text field, the system shall not trigger shortcuts.
- REQ-68 [always] The script editor shall offer line kinds "Fala", "Rubrica", "Texto não pertencente", "Cortada".
- REQ-69 [always] The system shall exclude "Texto não pertencente" lines from rehearsal display and listening.
- REQ-70 [event] When the actor changes a line's kind in the editor, the system shall save it (no failure mode beyond REQ-57).
- REQ-71 [always] The script editor shall let the actor fix character, kind and content of auto-parsed lines (existing editor kept; bulk select to set kind/character for several lines) (interpreted).
- REQ-72 [always] The system shall keep the parse / character detection pipeline unchanged.
- REQ-73 [always] The builder shall add small rehearsal UX improvements and list them in its report (F-23).

## Quality requirements
```
Q-36  Tag: Edit.Persistence
      Scale: edits made in rehearsal missing after reload / in the editor
      Meter: automated, 5 edits of each type
      Must: 0   Plan: 0
Q-37  Tag: Layout.Stability
      Scale: px the nav buttons move between lines (short vs >1000-char line)
      Meter: automated bounding box comparison
      Must: 0   Plan: 0
Q-38  Tag: Jump.Speed
      Scale: ms from "Saltar para aqui" to rehearsal resuming at the line
      Meter: automated, 5 trials
      Must: ≤1000   Plan: ≤300
Q-39  Tag: Edit.Flow
      Scale: clicks to reassign a line to another character during rehearsal
      Meter: human
      Must: ≤4   Plan: ≤2
Q-40  Tag: Skip.Correctness
      Scale: non-cue AI lines played while Modo Saltar is on
      Meter: automated
      Must: 0   Plan: 0
```
