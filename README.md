# cjm-session-scratchpad-qt

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

The session scratchpad — composition seat v0 of the seat family (DECs 2a062aff + ea85eab7). A model-agnostic Qt surface for composing LLM session messages in markdown: session-key file naming from .cjm/current-session (kills the copy-previous + rename rituals), a one-key edit/rendered toggle held position-stable in both directions by per-block source-line anchors in the owned markdown->HTML pipeline, autosave-only persistence (debounced idle + toggle/focus-loss/close, atomic writes, watcher guard — no dialogs), and wrap-selection formatting verbs on the KeymapRegistry lane. Designed for accretion: live-session feature filings land on-graph and build in later sittings.

## Modules

- **`cjm_session_scratchpad_qt.__init__`** — Session scratchpad — composition seat v0 (DEC 2a062aff + ea85eab7). Model-agnostic by design: any LLM session's message composition surface.
- **`cjm_session_scratchpad_qt.app`** — The scratchpad shell: composition seat v0 (DECs 2a062aff + ea85eab7).
- **`cjm_session_scratchpad_qt.appv2`** — The graph-rung scratchpad shell: composition seat v2 (DEC 6e76c120).
- **`cjm_session_scratchpad_qt.cli`** — CLI entry for the session scratchpad (console script `cjm-session-scratchpad-qt`).
- **`cjm_session_scratchpad_qt.files`** — Session-aware file resolution (DEC ea85eab7 pts 1-2).
- **`cjm_session_scratchpad_qt.graph`** — One open graph behind the scratchpad — the workbench GraphSession pattern
- **`cjm_session_scratchpad_qt.manifest`** — Pending-send manifests + pull-time reconciliation (DEC fc6a0cdc pt 5).
- **`cjm_session_scratchpad_qt.render`** — The owned markdown -> HTML pipeline (DEC ea85eab7 pt 4).
- **`cjm_session_scratchpad_qt.textops`** — Wrap-selection formatting operators (scope DEC 2a062aff pt 4) + the v2
- **`cjm_session_scratchpad_qt.timeline`** — Interleaved timeline derivation — the pure half of the v2 reading view.
- **`cjm_session_scratchpad_qt.timeline_html`** — Timeline HTML assembly — the pure presentation half of the v2 reading view.
- **`cjm_session_scratchpad_qt.watcher`** — Transcript-dir change detection — the sleep-first mtime poll's pure half.

## API

### `cjm_session_scratchpad_qt.app`

- `Editor` _class_ — The source pane, with line-addressed viewport access for the toggle.
- `ScratchpadWindow` _class_ — One session file behind an edit/rendered toggle.
- `block_line_map` _function_ — Scan a rendered document for the renderer's Lxx anchors:
- `mono_family` _function_ — The rendered code font: the theme's mono token, else the system

### `cjm_session_scratchpad_qt.appv2`

- `GraphScratchpadWindow` _class_ — One session spine behind a timeline + part-composer.
- `LanguageBar` _class_ — The fence-language mini-bar: a completer-backed field; Enter applies,
- `SessionPickerDialog` _class_ — The open-session gesture's chooser: filterable Session list, newest

### `cjm_session_scratchpad_qt.cli`

- `build_parser` _function_
- `main` _function_

### `cjm_session_scratchpad_qt.files`

- `Target` _class_
- `atomic_write` _function_ — temp + rename in the target dir: a mid-session agent read never sees
- `ensure_file` _function_ — Create the file blank if missing (sessions are born blank now);
- `find_session_key` _function_ — Walk up from `start` for the nearest `.cjm/current-session` pointer.
- `find_session_root` _function_ — The nearest pointer AND the project directory that owns it:
- `most_recent` _function_ — Newest markdown file by mtime (the absent-pointer fallback).
- `parse_key_time` _function_ — A session key is its mint timestamp; None for legacy/free-form names.
- `resolve_target` _function_ — The launch contract: explicit path wins; otherwise the session

### `cjm_session_scratchpad_qt.graph`

- `ScratchpadSession` _class_ — Sync facade over the projection layer for ONE session's scratchpad:
- `default_transcript_dir` _function_ — The harness transcript dir for a project: `~/.claude/projects/<slug>`,
- `part_payload` _function_ — A composer part's mint/journal payload: composer-minted uuid (the

### `cjm_session_scratchpad_qt.manifest`

- `PendingSend` _class_ — One recorded compose-send awaiting its transcript echo.
- `compose_text` _function_ — The outgoing message: parts joined as paragraphs, outer whitespace trimmed.
- `load_pending` _function_ — Read manifests; a missing or unreadable sidecar is an empty list.
- `manifest_path` _function_ — The session's pending-send sidecar.
- `reconcile` _function_ — Match manifests against pulled user messages by EXACT text.
- `save_pending` _function_ — Persist manifests atomically (temp + rename; a concurrent read never

### `cjm_session_scratchpad_qt.render`

- `RenderResult` _class_
- `nearest_anchor` _function_ — The anchor line for a source position: greatest anchor <= line
- `render_html` _function_ — Render markdown to QTextBrowser-ready HTML with per-block source-line

### `cjm_session_scratchpad_qt.textops`

- `WrapResult` _class_
- `fence_selection` _function_ — Toggle a code fence around the selected lines. An already-fenced block
- `toggle_list` _function_ — Toggle list markers on the selected lines: strip when every non-blank
- `wrap_selection` _function_ — Toggle `marker` around [start, end) of `document`.

### `cjm_session_scratchpad_qt.timeline`

- `TimelineEntry` _class_ — One timeline row, presentation-ready.
- `build_timeline` _function_ — Derive the interleaved timeline: active-path status + birth-class flags,
- `timeline_blocks` _function_ — Group consecutive off-path entries for the superseded-branch chip:

### `cjm_session_scratchpad_qt.timeline_html`

- `build_timeline_html` _function_ — The whole timeline document: cards separated by rules, consecutive
- `card_html` _function_ — One message card: anchored header line (identity + affordances) +
- `lane_filter` _function_ — The lane views: composition = composer-born, transcript = pulled.
- `linkify_ids` _function_ — Wrap full node/source ids appearing as text in jump:// links —

### `cjm_session_scratchpad_qt.watcher`

- `DirWatch` _class_ — Cheap (mtime, size) fingerprint over a transcript dir's *.jsonl.

## Dependencies

**Depends on:** `PySide6`, `cjm-context-graph-layer`, `cjm-context-graph-primitives`, `cjm-context-graph-projection`, `cjm-substrate-qt-kit`
