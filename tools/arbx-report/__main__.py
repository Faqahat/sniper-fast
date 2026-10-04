"""`python3 tools/arbx-report <command> ...` runs the CLI without installing (same as `python3 -m arbx_report`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arbx_report.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
