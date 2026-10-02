"""Loopback-only launcher for the installed application."""

import argparse
import os
import threading
import webbrowser
from pathlib import Path


def main():
    from platformdirs import user_data_path

    parser = argparse.ArgumentParser(description="Run the local TQEC Studio workspace.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("STUDIO_PORT", "5187")))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(
            os.environ.get("STUDIO_DATA_DIR", user_data_path("TQEC Studio", appauthor=False))
        ),
    )
    parser.add_argument(
        "--no-browser", action="store_true", default=bool(os.environ.get("STUDIO_NO_BROWSER"))
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    os.umask(0o077)
    args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.data_dir.chmod(0o700)
    os.environ.setdefault("MPLCONFIGDIR", str(args.data_dir / "matplotlib-cache"))
    from werkzeug.serving import make_server

    from studio import create_studio_app

    app = create_studio_app(args.data_dir)
    try:
        server = make_server("127.0.0.1", args.port, app, threaded=True)
    except OSError as exc:
        parser.exit(1, f"Unable to start Studio: {exc}\n")
    url = f"http://127.0.0.1:{args.port}"
    print(f"TQEC Studio: {url}", flush=True)
    print(f"Local data: {args.data_dir}", flush=True)
    timer = None
    if not args.no_browser:
        timer = threading.Timer(0.5, lambda: webbrowser.open(url))
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if timer:
            timer.cancel()
        server.server_close()
        app.extensions["studio_executor"].shutdown(wait=True)
