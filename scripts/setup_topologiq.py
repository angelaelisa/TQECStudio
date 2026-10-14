"""Install the optional engine separately from Studio's Python dependencies."""

import subprocess
import sys
import tempfile
import urllib.request
import venv
from pathlib import Path
from zipfile import ZipFile

TOPOLOGIQ_REVISION = "d010bd3e63686c93c12c922a84a944a3386ac785"


def extract_windows_source(archive, destination):
    """Stage the pinned source without Windows' reserved AUX filenames."""
    destination = Path(destination)
    with ZipFile(archive) as source:
        for item in source.infolist():
            parts = Path(item.filename).parts
            if ".." in parts or Path(item.filename).is_absolute():
                raise ValueError("Invalid source archive path.")
            target = destination.joinpath(*parts)
            if target.name.lower() == "aux.py":
                target = target.with_name("platform_aux.py")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = source.read(item)
            if target.suffix == ".py":
                # The upstream checkout has two AUX modules. This changes
                # their names and references, not the lattice-surgery rules.
                contents = (
                    contents.decode("utf-8")
                    .replace(".aux import", ".platform_aux import")
                    .encode("utf-8")
                )
            target.write_bytes(contents)
    roots = [path for path in destination.iterdir() if (path / "pyproject.toml").is_file()]
    if len(roots) != 1:
        raise ValueError("Expected one Topologiq source directory.")
    return roots[0]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    environment = root / ".venv-topologiq"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    with tempfile.TemporaryDirectory() as folder:
        package = f"git+https://github.com/tqec/topologiq.git@{TOPOLOGIQ_REVISION}"
        if sys.platform == "win32":
            archive = Path(folder) / "source.zip"
            urllib.request.urlretrieve(
                f"https://codeload.github.com/tqec/topologiq/zip/{TOPOLOGIQ_REVISION}", archive
            )
            package = str(extract_windows_source(archive, Path(folder) / "source"))
        subprocess.run([str(python), "-m", "pip", "install", package], check=True)
    print(f"Topologiq installed in {environment}. Restart Studio to use it.")
