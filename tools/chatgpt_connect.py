"""Windows connection wizard and isolated subscription OCR feasibility check.

Build: python -m PyInstaller --onefile --windowed --paths app/backend
       --name KnittingLibrary-ChatGPT tools/chatgpt_connect.py
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from app.ai.chatgpt_protocol import (
    ChatGPTError, authorization_url, finish_sign_in, infer, list_models,
    new_transfer_key, open_connection, refresh_credentials, response_payload, seal_connection,
)


def sign_in(setup: dict, on_status, opener=webbrowser.open) -> dict:
    result = {}
    expected_state = ""

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # OAuth query parameters must never enter logs.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            state = query.get("state", [""])[0]
            if parsed.path != "/auth/callback" or not secrets.compare_digest(state, expected_state):
                self.send_error(400, "Invalid sign-in callback")
                return
            result.update({key: values[0] for key, values in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Return to the Knitting Library connection helper. You can close this tab.")

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        url, verifier, expected_state = authorization_url(setup["host_id"], setup["nonce"], redirect,
                                                         setup.get("client_id") or "dynamic_agent_client")
        on_status("Complete sign-in and approve ChatGPT plan usage in your browser.")
        if not opener(url):
            raise ChatGPTError("browser_unavailable", "Could not open your system browser.")
        deadline = min(time.time() + 600, setup["expires_at"])
        while not result and time.time() < deadline:
            server.handle_request()
        if not result:
            raise ChatGPTError("sign_in_timeout", "Sign-in timed out. Start again.")
        if result.get("error"):
            raise ChatGPTError("consent_declined", "ChatGPT sign-in or plan usage was declined.")
        return finish_sign_in(result.get("code", ""), result.get("client_id") or setup.get("client_id", ""),
                              verifier, redirect, setup["nonce"])


def diagnostic(image: Path, on_status) -> dict:
    """No persisted credentials: test sign-in, refresh, encrypted transfer, then OCR."""
    private, public = new_transfer_key()
    setup = {"version": 1, "host_id": "urn:uuid:" + str(uuid.uuid4()), "attempt_id": str(uuid.uuid4()),
             "nonce": secrets.token_urlsafe(32), "expires_at": time.time() + 900, "public_key": public}
    credentials = sign_in(setup, on_status)
    on_status("Checking token renewal and encrypted server transfer...")
    credentials = refresh_credentials(credentials)
    transferred = open_connection(setup, seal_connection(setup, credentials), private)
    models = list_models(transferred["access_token"])
    if not models:
        raise ChatGPTError("no_models", "No models are available for this account.")
    preferred = next((item for item in models if item["id"] == "gpt-6.1-sol"), models[0])
    on_status("Testing image transcription with " + preferred["name"] + "...")
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    image_url = "data:" + mime + ";base64," + base64.b64encode(image.read_bytes()).decode()
    result = infer(transferred["access_token"], response_payload(preferred["id"],
                   "Transcribe the knitting recipe text in this image faithfully. Return only the text.", image_url))
    if not result["text"].strip():
        raise ChatGPTError("empty_ocr", "The image test returned no text.")
    return {"success": True, "model": preferred["id"], "characters": len(result["text"]),
            "refresh_verified": True, "encrypted_transfer_verified": True, "usage": result["usage"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.title("Knitting Library — ChatGPT connection")
    root.geometry("620x310")
    root.resizable(False, False)
    status = tk.StringVar(value="Sign in with your ChatGPT account. Your password stays with OpenAI.")
    tk.Label(root, text="ChatGPT subscription OCR", font=("Segoe UI", 18, "bold")).pack(pady=(24, 12))
    tk.Label(root, textvariable=status, wraplength=560, font=("Segoe UI", 11), justify="left").pack(padx=30, pady=10)
    tk.Label(root, text="This uses your ChatGPT plan or available credits.\nNo API key or existing Codex credentials are used.",
             font=("Segoe UI", 10)).pack(pady=10)

    def update_status(value):
        root.after(0, status.set, value)

    def completed(result):
        button.config(state="normal")
        if args.diagnostic:
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            status.set("Verified sign-in, token refresh, encrypted transfer and image OCR with " + result["model"] + ".")
        else:
            output = filedialog.asksaveasfilename(title="Save encrypted connection for your NAS", defaultextension=".kl-chatgpt",
                                                  initialfile="knitting-library.kl-chatgpt")
            if output:
                Path(output).write_text(json.dumps(result), encoding="utf-8")
                status.set("Upload the encrypted connection file in your NAS AI settings. Then delete this local file.")

    def failed(code, message):
        button.config(state="normal")
        status.set(message)
        if args.diagnostic and args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({"success": False, "code": code}), encoding="utf-8")
        messagebox.showerror("Connection not completed", message)

    def start():
        image, setup = args.image, None
        if args.diagnostic:
            if image is None:
                selected = filedialog.askopenfilename(title="Choose a recipe image", filetypes=[("Recipe images", "*.png *.jpg *.jpeg")])
                if not selected:
                    return
                image = Path(selected)
        else:
            selected = filedialog.askopenfilename(title="Open the setup package from your NAS", filetypes=[("Setup package", "*.kl-setup")])
            if not selected:
                return
            try:
                setup = json.loads(Path(selected).read_text(encoding="utf-8"))
                if setup.get("version") != 1 or setup.get("expires_at", 0) < time.time():
                    raise ValueError()
            except Exception:
                messagebox.showerror("Invalid setup", "Download a fresh setup package from your NAS AI settings.")
                return
        button.config(state="disabled")

        def run():
            try:
                result = diagnostic(image, update_status) if args.diagnostic else seal_connection(setup, sign_in(setup, update_status))
                root.after(0, completed, result)
            except ChatGPTError as exc:
                root.after(0, failed, exc.code, str(exc))
            except Exception:
                root.after(0, failed, "connection_failed", "Connection failed. Start again with a fresh setup package.")
        threading.Thread(target=run, daemon=True).start()

    button = tk.Button(root, text="Continue with ChatGPT", command=start, font=("Segoe UI", 11), padx=18, pady=7)
    button.pack(pady=14)
    root.mainloop()


if __name__ == "__main__":
    main()
