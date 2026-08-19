# cjm-session-scratchpad-qt

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

The session scratchpad — composition seat v0 of the seat family (DECs 2a062aff + ea85eab7). A model-agnostic Qt surface for composing LLM session messages in markdown: session-key file naming from .cjm/current-session (kills the copy-previous + rename rituals), a one-key edit/rendered toggle held position-stable in both directions by per-block source-line anchors in the owned markdown->HTML pipeline, autosave-only persistence (debounced idle + toggle/focus-loss/close, atomic writes, watcher guard — no dialogs), and wrap-selection formatting verbs on the KeymapRegistry lane. Designed for accretion: live-session feature filings land on-graph and build in later sittings.

## Modules

- **`cjm_session_scratchpad_qt`** — Session scratchpad — composition seat v0 (DEC 2a062aff + ea85eab7). Model-agnostic by design: any LLM session's message composition surface.
- **`cjm_session_scratchpad_qt.app`** — The scratchpad shell: composition seat v0 (DECs 2a062aff + ea85eab7).
- **`cjm_session_scratchpad_qt.cli`** — CLI entry for the session scratchpad (console script `cjm-session-scratchpad-qt`).
- **`cjm_session_scratchpad_qt.files`** — Session-aware file resolution (DEC ea85eab7 pts 1-2).
- **`cjm_session_scratchpad_qt.render`** — The owned markdown -> HTML pipeline (DEC ea85eab7 pt 4).
- **`cjm_session_scratchpad_qt.textops`** — Wrap-selection formatting operators (scope DEC 2a062aff pt 4).

## API

### `cjm_session_scratchpad_qt.app`

- `Editor` _class_ — The source pane, with line-addressed viewport access for the toggle.
- `ScratchpadWindow` _class_ — One session file behind an edit/rendered toggle.
- `block_line_map` _function_ — Scan a rendered document for the renderer's Lxx anchors:
- `mono_family` _function_ — The rendered code font: the theme's mono token, else the system

### `cjm_session_scratchpad_qt.cli`

- `build_parser` _function_
- `main` _function_

### `cjm_session_scratchpad_qt.files`

- `Target` _class_
- `atomic_write` _function_ — temp + rename in the target dir: a mid-session agent read never sees
- `ensure_file` _function_ — Create the file blank if missing (sessions are born blank now);
- `find_session_key` _function_ — Walk up from `start` for the nearest `.cjm/current-session` pointer.
- `most_recent` _function_ — Newest markdown file by mtime (the absent-pointer fallback).
- `parse_key_time` _function_ — A session key is its mint timestamp; None for legacy/free-form names.
- `resolve_target` _function_ — The launch contract: explicit path wins; otherwise the session

### `cjm_session_scratchpad_qt.render`

- `RenderResult` _class_
- `nearest_anchor` _function_ — The anchor line for a source position: greatest anchor <= line
- `render_html` _function_ — Render markdown to QTextBrowser-ready HTML with per-block source-line

### `cjm_session_scratchpad_qt.textops`

- `WrapResult` _class_
- `wrap_selection` _function_ — Toggle `marker` around [start, end) of `document`.

## Dependencies

**Depends on:** `PySide6`, `cjm-substrate-qt-kit`
