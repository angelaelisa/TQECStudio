"""Install the optional engine separately from Studio's Python dependencies."""

import subprocess
import sys
import venv
from pathlib import Path

TOPOLOGIQ_REVISION = "d010bd3e63686c93c12c922a84a944a3386ac785"

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    environment = root / ".venv-topologiq"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            f"git+https://github.com/tqec/topologiq.git@{TOPOLOGIQ_REVISION}",
        ],
        check=True,
    )
    print(f"Topologiq installed in {environment}. Restart Studio to use it.")
