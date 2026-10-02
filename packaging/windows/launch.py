"""Frozen entry point: divert simulation workers before loading the GUI."""

import multiprocessing
import os
import sys

if __name__ == "__main__":
    # Windowed builds lack console streams; decoder workers still need them.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from studio.windows_smoke import run

        run(sys.argv[2])
    else:
        from studio.desktop import main

        main()
