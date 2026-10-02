# Windows tester application

The Windows preview is a portable folder containing **TQEC Studio.exe**, its bundled Python runtime and scientific libraries. Testers do not need Python, a terminal, or coding knowledge. Extract the complete ZIP and double-click the executable; a small launcher window opens the local browser interface. Keep the folder's `_internal` directory beside the executable.

The launcher provides **Open Studio** and **Stop Studio**. Stop asks the user to save their project and waits for running jobs to finish. Output files and the launcher log live in `%LOCALAPPDATA%\TQEC Studio`, separate from the downloaded application. The browser draft remains tied to the normal Studio address and browser. The executable listens only on `127.0.0.1:5187`; simultaneous copies produce an actionable startup error.

## Produce a tester download

After the source is in the repository:

1. Open **Actions → Build Windows tester app → Run workflow**.
2. Wait for installation, source tests, packaging and frozen executable checks to pass.
3. Download the **TQEC-Studio-Windows-Testers** artifact from that run.
4. Extract the artifact to obtain `TQEC-Studio-Windows-Testers.zip` and its SHA-256 checksum. Supply this inner ZIP to testers.

The workflow is manual and does not publish a GitHub Release. Artifact retention is 14 days. Original Studio code is licensed under Apache-2.0; bundled dependencies retain their own terms. This unsigned preview is not an official TQEC release.

The automated frozen check verifies packaged static files, a real TQEC memory compilation, Crumble, physical-layer SVG output and a spawned PyMatching sampling worker. Before distribution, also test on a Windows computer with no Python installed: launch, browser opening, graph edits, save/import, plot generation, and stopping the launcher. CI does not establish visual usability, signing or Windows compatibility by itself.

## Build directly on Windows

Use 64-bit Python 3.13 in a clean checkout:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging/windows/studio.spec
```

The output is `dist\TQEC Studio\TQEC Studio.exe`. Include the whole folder when distributing, plus `packaging/windows/START-HERE.txt`, `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`. Run `python scripts/collect_licenses.py --output "dist/TQEC Studio/third_party_licenses" --include-runtime` in the build environment to include dependency and Python/Tcl/Tk licence texts. A folder bundle is used so the runtime and scientific dependencies do not need to unpack on every launch. Builds are platform-specific; this Windows executable cannot be produced by running PyInstaller directly on macOS.

## Current verification status

The packaging source and manual workflow are prepared. A Windows executable is not considered ready until the actual Windows build and frozen checks pass. GUI startup/shutdown and use on a clean Windows machine require a separate manual check. Signed installers and automatic updates are outside this tester build.
