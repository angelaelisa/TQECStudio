"""Export only approved source files, without Git history or local user data."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

FILES = {
    ".gitignore",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    "MANIFEST.in",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "requirements.txt",
    "requirements.lock",
    "run_studio.py",
    "Launch Studio.command",
}
DIRECTORIES = {".github", "docs", "scripts", "studio", "tests", "packaging"}
SUFFIXES = {".py", ".js", ".cjs", ".css", ".html", ".svg", ".md", ".yml", ".yaml", ".spec", ".txt"}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "cloud access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "personal absolute path": re.compile(r"(?:/Users/|/home/)[A-Za-z0-9_.-]+/"),
}


def source_files(root):
    selected = [root / name for name in sorted(FILES)]
    for name in sorted(DIRECTORIES):
        selected.extend(
            sorted(
                p
                for p in (root / name).rglob("*")
                if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts
            )
        )
    for path in selected:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or symlinked source file: {path.relative_to(root)}")
        text = path.read_text()
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                raise ValueError(
                    f"{label} detected in {path.relative_to(root)}; review before export."
                )
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    paths = source_files(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "tqec-studio/" + str(path.relative_to(root)))
        archive.writestr("tqec-studio/SOURCE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{digest}  {args.output.name}\n"
    )
    print(f"Exported {len(paths)} source files to {args.output}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
