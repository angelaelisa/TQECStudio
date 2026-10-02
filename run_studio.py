"""Source-checkout launcher. Existing development runs stay in instance/studio."""

import os
from pathlib import Path

from studio.cli import main

if __name__ == "__main__":
    os.environ.setdefault(
        "STUDIO_DATA_DIR", str(Path(__file__).resolve().parent / "instance" / "studio")
    )
    main()
