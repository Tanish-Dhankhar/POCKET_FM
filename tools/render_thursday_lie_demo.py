"""Generate the standalone ``The Thursday Lie`` presentation series.

This project deliberately shares the hardened story/audio builder and global
content caches with ``The Other Key`` while persisting to its own series folder.
Artwork, episode records, stems, and the final master remain project-local.
"""
from __future__ import annotations

from tools import render_infidelity_demo as demo


SERIES_ID = "the-thursday-lie-demo"
TITLE = "The Thursday Lie"


def main() -> int:
    demo.SERIES_ID = SERIES_ID
    demo.TITLE = TITLE
    return demo.main()


if __name__ == "__main__":
    raise SystemExit(main())
