# Desktop preview downloads

Download release **0.1.0rc2** from [GitHub Releases](https://github.com/angelaelisa/TQECStudio/releases/tag/v0.1.0rc2). Downloads are public and include Python and scientific dependencies; no terminal or Python installation is required.

| Package | Computer |
| --- | --- |
| Windows | Windows 10/11, x64 Intel or AMD |
| Mac Apple Silicon | Apple M-series chip, macOS 14 or later |
| Mac Intel | Intel processor, macOS 15 or later |

These targets describe the preview builds; other architectures and older Mac versions are not covered. On Mac, **Apple menu → About This Mac** identifies the chip or processor. CI runs on Windows Server and the named Mac versions; Windows 10/11 everyday use still needs tester feedback.

## Start Studio

On Windows, right-click the ZIP and choose **Extract All**. Open the extracted **TQEC Studio** folder and double-click **TQEC Studio.exe**. Keep `_internal` and the rest of the folder together. Do not launch from inside the ZIP.

On Mac, double-click the ZIP to extract it. Open the extracted folder, move **TQEC Studio.app** to Applications and open it. Keep the included licence documents with the original download.

The launcher opens Studio in your usual browser at `http://127.0.0.1:5187/`. Keep the launcher open while working. Use **Open Studio** to reopen the browser, **Save project** to download your graph, then **Stop Studio** when finished. Running jobs finish before the launcher closes.

## Preview security prompts

Windows builds are unsigned. If Windows blocks opening the app, contact the project owner for a verified package.

Mac previews are ad-hoc signed by the packaging tool, without an Apple Developer ID or Apple notarization. Gatekeeper may block opening them. If you trust the release, use **System Settings → Privacy & Security → Open Anyway**, then confirm Open. If that option is unavailable, contact the project owner. Do not disable Gatekeeper globally.

A future release with fewer security prompts requires Windows code signing and Apple Developer ID signing/notarization. The preview does not include those credentials.

## Checks and troubleshooting

Each ZIP includes `build-check.json` from the bundled executable’s automatic checks: launcher runtime, static assets, compilation, physical qubit slices, Crumble, sampling and PNG/SVG plot exports. `third_party_licenses/` contains the upstream notices and licence texts. The adjacent `.sha256` file records the ZIP checksum.

Automated checks verify bundled functions on the build machines. They do not prove that every configuration or tester computer works. Report issues with operating system version, package name and what you clicked; include the launcher log or browser console error after checking for private data.

If Studio cannot start, close any other copy using port 5187. Logs:

- Windows: `%LOCALAPPDATA%\TQEC Studio\launcher.log`
- Mac: `~/Library/Application Support/TQEC Studio/launcher.log`

Compilation and simulation run locally. Saved results use the platform’s application-data directory; browser drafts belong to the browser you use. Use **Save project** before changing browsers or removing the app. TQEC-exported 3D HTML viewers may require internet access for their Three.js modules.

See the [user guide](USER_GUIDE.md) for the design and compilation workflow.
