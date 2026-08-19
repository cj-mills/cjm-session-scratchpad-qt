"""CLI entry for the session scratchpad (console script `cjm-session-scratchpad-qt`)."""

import argparse
import sys
from pathlib import Path

from cjm_substrate_qt_kit.theme import apply_theme
from PySide6.QtWidgets import QApplication

from .app import ScratchpadWindow
from .files import resolve_target, SCRATCHPAD_DIR


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cjm-session-scratchpad-qt",
        description="Session scratchpad (composition seat v0): no args opens this "
                    "session's file — .cjm/current-session resolved upward from cwd, "
                    "named into the scratchpad dir; a path argument opens any file "
                    "(previous sessions, _carryover.md).")
    p.add_argument("path", nargs="?", default=None,
                   help="Open this file instead of the session's scratchpad")
    p.add_argument("--dir", default=None,
                   help=f"Scratchpad directory (default: {SCRATCHPAD_DIR})")
    return p


def main() -> int:
    args = build_parser().parse_args()
    directory = Path(args.dir).expanduser() if args.dir else SCRATCHPAD_DIR
    target = resolve_target(Path.cwd(), args.path, directory)
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    window = ScratchpadWindow(target.path, banner=target.banner, directory=directory)
    window.show()
    return app.exec()


if __name__ == "__main__":  # runtime-order: must trail every def (python -m executes in slot order)
    sys.exit(main())
