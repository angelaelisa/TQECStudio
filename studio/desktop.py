"""Small desktop launcher for a bundled local Studio, with no console required."""

import logging
import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path


def main():
    import tkinter as tk
    from tkinter import messagebox, ttk

    from platformdirs import user_data_path

    os.umask(0o077)
    data = Path(user_data_path("TQEC Studio", appauthor=False))
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(data / "matplotlib-cache"))
    log = data / "launcher.log"
    stream = log.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    logging.basicConfig(stream=stream, level=logging.INFO)
    window = tk.Tk()
    window.title("TQEC Studio")
    window.geometry("440x260")
    window.minsize(400, 240)
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="◈ TQEC Studio", font=("Segoe UI", 18)).pack(anchor="w")
    state = tk.StringVar(value="Starting Studio…")
    ttk.Label(frame, textvariable=state, wraplength=380).pack(anchor="w", pady=16)
    ttk.Label(frame, text="Keep this window open while using Studio.", wraplength=380).pack(
        anchor="w"
    )
    events = queue.Queue()
    server = None
    app = None
    url = None
    stopping = False

    def open_browser():
        if url:
            webbrowser.open(url)

    def stop():
        nonlocal stopping
        if stopping:
            return
        if server is None:
            if app is None and url is None and open_button["state"] == "disabled":
                if state.get().startswith("Starting"):
                    messagebox.showinfo("Starting Studio", "Please wait for Studio to start.")
                    return
            window.destroy()
            return
        if not messagebox.askokcancel(
            "Stop Studio",
            "Save your project in the browser before stopping.\n\n"
            "Running compilation or simulation jobs will finish before Studio closes.",
        ):
            return
        stopping = True
        open_button.configure(state="disabled")
        stop_button.configure(state="disabled")
        state.set("Stopping Studio. Waiting for any running jobs to finish…")

        def shutdown():
            server.shutdown()
            server.server_close()
            app.extensions["studio_executor"].shutdown(wait=True)
            events.put(("stopped", None))

        threading.Thread(target=shutdown, daemon=True).start()

    open_button = ttk.Button(frame, text="Open Studio", command=open_browser, state="disabled")
    open_button.pack(side="left", pady=20)
    stop_button = ttk.Button(frame, text="Stop Studio", command=stop)
    stop_button.pack(side="right", pady=20)
    window.protocol("WM_DELETE_WINDOW", stop)

    def start():
        instance = None
        try:
            from werkzeug.serving import make_server

            from studio import create_studio_app

            instance = create_studio_app(data)
            listener = make_server("127.0.0.1", 5187, instance, threaded=True)
            events.put(("ready", (instance, listener)))
            listener.serve_forever()
        except (Exception, SystemExit):
            logging.exception("Studio failed to start")
            if instance is not None:
                instance.extensions["studio_executor"].shutdown(wait=False)
            events.put(
                (
                    "error",
                    "Studio could not start. If Studio is already open, close it first.\n\n"
                    f"Details are saved in:\n{log}",
                )
            )

    def poll():
        nonlocal app, server, url
        try:
            while True:
                event, value = events.get_nowait()
                if event == "ready":
                    app, server = value
                    url = "http://127.0.0.1:5187/"
                    state.set(
                        "Studio is running on your computer. Your browser opens automatically."
                    )
                    open_button.configure(state="normal")
                    open_browser()
                elif event == "error":
                    state.set("Studio could not start. See the error details.")
                    messagebox.showerror("TQEC Studio", value)
                elif event == "stopped":
                    window.destroy()
                    return
        except queue.Empty:
            pass
        window.after(150, poll)

    threading.Thread(target=start, daemon=True).start()
    window.after(150, poll)
    window.mainloop()
