"""Bundle original dependency licence files for a portable binary distribution."""

import argparse
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(destination, include_runtime=False):
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for name, version in re.findall(
        r"^([\w-]+)==([^\s]+)", (ROOT / "requirements.lock").read_text(), re.M
    ):
        dist = metadata.distribution(name)
        if dist.version != version:
            raise ValueError(f"Expected {name} {version}, installed {dist.version}")
        folder = destination / f"{name}-{version}"
        folder.mkdir(exist_ok=True)
        copied = []
        for item in dist.files or []:
            lower = item.name.lower()
            relevant = lower.startswith(
                ("license", "licence", "copying", "notice", "authors", "copyright")
            ) or any(part.lower() in ("licenses", "licences") for part in item.parts)
            if not relevant:
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                raise ValueError(f"Missing recorded licence file: {name}/{item}")
            # Flatten the installed paths without retaining machine-specific directories.
            target = folder / (str(len(copied)) + "-" + item.name)
            shutil.copyfile(source, target)
            copied.append(target.name)
        fallback = ROOT / "packaging" / "licenses" / f"{name}-{version}"
        if not copied and fallback.is_dir():
            for source in sorted(fallback.iterdir()):
                if source.is_file():
                    shutil.copyfile(source, folder / source.name)
                    copied.append(source.name)
        if not copied:
            raise ValueError(f"No licence text found for {name} {version}")
        (folder / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
        records.append({"name": name, "version": version, "files": copied})
    if include_runtime:
        runtime = destination / "Python-runtime"
        runtime.mkdir(exist_ok=True)
        prefix = Path(sys.base_prefix)
        python_license = next(
            (prefix / n for n in ("LICENSE.txt", "LICENSE") if (prefix / n).is_file()), None
        )
        if python_license is None:
            raise ValueError("CPython runtime licence is missing")
        shutil.copyfile(python_license, runtime / "LICENSE.txt")
        import tkinter as tk

        window = tk.Tk()
        try:
            window.withdraw()
            runtime_versions = {
                component: str(window.tk.call("package", "provide", component.capitalize()))
                for component in ("tcl", "tk")
            }
        finally:
            window.destroy()
        for component in ("tcl", "tk"):
            candidates = sorted((prefix / "tcl").glob(component + "*/license.terms"))
            if not candidates:
                version = runtime_versions[component]
                fallback = ROOT / "packaging" / "licenses" / f"{component}-{version}"
                if not (fallback / "license.terms.txt").is_file():
                    raise ValueError(f"Bundled {component} {version} runtime licence is missing")
                shutil.copytree(fallback, runtime / f"{component}-{version}", dirs_exist_ok=True)
            for source in candidates:
                shutil.copyfile(source, runtime / (source.parent.name + "-license.terms"))
    (destination / "INDEX.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-runtime", action="store_true")
    args = parser.parse_args()
    records = collect(args.output, args.include_runtime)
    print(f"Collected licence texts for {len(records)} locked Python distributions.")
