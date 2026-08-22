"""CLI entry for the session scratchpad (console script `cjm-session-scratchpad-qt`).

Two rungs behind one command (DEC e8b2f397 pt 1 — session-boundary cutover,
migrate nothing): pass `--graph-db-path` and the session pointer's session
opens the GRAPH rung (part-composer + interleaved timeline over the spine);
without it — or with an explicit file argument — the file rung serves exactly
as before (existing scratchpads, `_carryover.md`, previous sessions). Graph
paths stay EXPLICIT (guardrail 027bbe56: dev `.cjm/` locations are
scaffolding, never baked-in defaults; wrappers bake them per graph)."""

import argparse
import sys
from pathlib import Path

from cjm_substrate_qt_kit.theme import apply_theme
from PySide6.QtWidgets import QApplication

from .app import ScratchpadWindow
from .files import find_session_root, resolve_target, SCRATCHPAD_DIR


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cjm-session-scratchpad-qt",
        description="Session scratchpad: with --graph-db-path, no args opens this "
                    "session's GRAPH-rung composition seat (.cjm/current-session "
                    "resolved upward from cwd); otherwise the file rung — no args "
                    "opens the session's file, a path argument opens any file.")
    p.add_argument("path", nargs="?", default=None,
                   help="Open this FILE (file rung) instead of the session seat")
    p.add_argument("--dir", default=None,
                   help=f"Scratchpad directory (default: {SCRATCHPAD_DIR})")
    p.add_argument("--graph-db-path", default=None,
                   help="Graph db path — enables the graph rung (always explicit)")
    p.add_argument("--journal-path", default=None,
                   help="The graph's writes journal (journal-first writes land here)")
    p.add_argument("--manifests-dir", default=None,
                   help="Capability manifests dir (default: the projection lib's)")
    p.add_argument("--transcript-dir", default=None,
                   help="Harness transcript dir (default: derived from the "
                        "session pointer's project root)")
    p.add_argument("--session", default=None,
                   help="Open this session KEY's spine (graph rung) instead of "
                        "the live pointer session — past-spine browsing; journal "
                        "attribution stays with the live session")
    p.add_argument("--any-boot", action="store_true",
                   help="Match transcripts without the minted-in-workbench boot "
                        "signal (resumed / manually booted sessions)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    directory = Path(args.dir).expanduser() if args.dir else SCRATCHPAD_DIR
    app = QApplication(sys.argv[:1])
    apply_theme(app)

    if args.graph_db_path and not args.path:
        found = find_session_root(Path.cwd())
        if found or args.session:
            # No pointer + explicit --session: that key serves as the live key
            # too (degenerate browse-only boot).
            key, root = found if found else (args.session, Path.cwd())
            # Deferred: the graph stack import is the graph rung's cost alone.
            from .appv2 import GraphScratchpadWindow
            from .graph import default_transcript_dir, ScratchpadSession
            transcript_dir = (Path(args.transcript_dir).expanduser()
                              if args.transcript_dir else default_transcript_dir(root))
            session = ScratchpadSession(
                args.graph_db_path, key, manifests_dir=args.manifests_dir,
                journal_paths=[args.journal_path] if args.journal_path else [])
            session.start()
            if args.session and args.session != key:
                session.rebind(args.session)  # browse target; live key still stamps
            window = GraphScratchpadWindow(
                session, transcript_dir=transcript_dir, directory=directory,
                banner=None if args.journal_path else
                "no --journal-path — writes will NOT survive a rebuild",
                require_signal=not args.any_boot, live_key=key)
            window.show()
            try:
                return app.exec()
            finally:
                session.close()
        banner = "no .cjm/current-session pointer — graph rung unavailable, file rung"
        target = resolve_target(Path.cwd(), None, directory)
        window = ScratchpadWindow(target.path, banner=target.banner or banner,
                                  directory=directory)
        window.show()
        return app.exec()

    target = resolve_target(Path.cwd(), args.path, directory)
    window = ScratchpadWindow(target.path, banner=target.banner, directory=directory)
    window.show()
    return app.exec()


if __name__ == "__main__":  # runtime-order: must trail every def (python -m executes in slot order)
    sys.exit(main())
