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

The automated frozen check initializes the bundled Tk GUI runtime and verifies packaged static files, a real TQEC memory compilation, Crumble, physical-layer SVG output, a real noise sweep using a spawned PyMatching sampling worker, and PNG/SVG plot exports with observable and threshold insets. Early testers should also check on a Windows computer with no Python installed: launch, browser opening, graph edits, save/import, plot generation, and stopping the launcher. CI does not establish visual usability or compatibility with every Windows computer.

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

The [2026-10-06 Windows build](https://github.com/angelaelisa/TQECStudio/actions/runs/37424276623), from source commit `669278ad4eaa2d60dd96fba2fa794fae77771342`, passed all 32 application tests and the frozen executable checks, including real PNG/SVG plot exports on GitHub's Windows x64 runner with Python 3.13.15. The download includes `build-check.json`, the Apache-2.0 licence, third-party notices, dependency licence texts, and Python/Tcl/Tk licence texts. A SHA-256 checksum accompanies the ZIP. Bundled JavaScript, CSS and SVG assets use fixed HTTP content types and are served without caching. The frozen checks deliberately supply incorrect system MIME mappings to verify that the Windows registry cannot prevent script execution.

Download the **TQEC-Studio-Windows-Testers** artifact from that run (GitHub sign-in is required). Artifacts expire after 14 days; retain the inner application ZIP to share directly with testers, or run the workflow again. Full launcher interaction, browser opening/shutdown and use on a clean Windows machine still require manual testing. Signed installers and automatic updates are outside this tester build.
