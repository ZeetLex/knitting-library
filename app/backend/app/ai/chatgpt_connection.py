"""Protected single-owner ChatGPT connection, independent of legacy service wiring."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.paths import DATA_ROOT
from app.ai import chatgpt_protocol as protocol

_THREAD_LOCK = threading.RLock()
USAGE_URL = "https://chatgpt.com/settings/usage"


def _directory() -> Path:
    directory = DATA_ROOT / ".chatgpt"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


@contextlib.contextmanager
def locked():
    """Serialize refresh/import/revoke across threads and server processes."""
    with _THREAD_LOCK:
        path = _directory() / "connection.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+b") as handle:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic(path: Path, content: bytes):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _key() -> bytes:
    path = _directory() / "storage.key"
    if not path.exists():
        _atomic(path, AESGCM.generate_key(bit_length=256))
    return path.read_bytes()


def _read(name: str) -> dict | None:
    path = _directory() / (name + ".enc")
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        return json.loads(AESGCM(_key()).decrypt(raw[:12], raw[12:], name.encode()))
    except Exception:
        raise protocol.ChatGPTError("credential_storage_error", "The protected ChatGPT connection could not be read.") from None


def _write(name: str, value: dict):
    nonce = secrets.token_bytes(12)
    _atomic(_directory() / (name + ".enc"), nonce + AESGCM(_key()).encrypt(nonce, json.dumps(value).encode(), name.encode()))


def _host_id() -> str:
    path = _directory() / "host-id"
    if not path.exists():
        _atomic(path, ("urn:uuid:" + str(uuid.uuid4())).encode())
    return path.read_text(encoding="utf-8")


def connection() -> dict | None:
    with locked():
        return _read("connection")


def status() -> dict:
    with locked():
        record = _read("connection")
        if not record:
            return {"connected": False, "usage_url": USAGE_URL}
        return {"connected": True, "connection_id": record["connection_id"], "email": record.get("email", ""),
                "owner_id": record["owner_id"], "owner_name": record["owner_name"],
                "health": record.get("health", "connected"), "models": record.get("models", []), "usage_url": USAGE_URL}


def begin_setup(owner: dict) -> dict:
    with locked():
        private, public = protocol.new_transfer_key()
        current = _read("connection")
        attempt = {"version": 1, "attempt_id": str(uuid.uuid4()), "host_id": _host_id(),
                   "nonce": secrets.token_urlsafe(32), "public_key": public, "private_key": private,
                   "expires_at": time.time() + 900, "owner_id": owner["id"], "owner_name": owner["username"]}
        if current and current["owner_id"] == owner["id"]:
            attempt["client_id"] = current["credentials"]["client_id"]
        _write("setup", attempt)
        return {key: value for key, value in attempt.items() if key not in {"private_key", "owner_id", "owner_name"}}


def import_connection(envelope: dict, owner: dict) -> dict:
    with locked():
        attempt = _read("setup")
        if not attempt or attempt["owner_id"] != owner["id"]:
            raise protocol.ChatGPTError("invalid_setup", "Start a new connection setup from this admin account.")
        credentials = protocol.open_connection(attempt, envelope, attempt["private_key"])
        client_id = credentials.get("client_id", "")
        if not client_id or client_id == "dynamic_agent_client":
            raise protocol.ChatGPTError("invalid_registration")
        identity = protocol.validate_identity(credentials.get("id_token", ""), client_id, attempt["nonce"])
        if protocol.PLAN_SCOPE not in credentials.get("scope", "").split():
            raise protocol.ChatGPTError("plan_permission_missing")
        # A successful refresh verifies that these transferred credentials are renewable.
        credentials = protocol.refresh_credentials(credentials)
        models = protocol.list_models(credentials["access_token"])
        if not models:
            raise protocol.ChatGPTError("no_models", "No ChatGPT models are available to this account.")
        _write("connection", {"connection_id": str(uuid.uuid4()), "owner_id": owner["id"],
               "owner_name": owner["username"], **identity, "credentials": credentials,
               "models": models, "health": "connected"})
        (_directory() / "setup.enc").unlink(missing_ok=True)
    return status()


def access_token(expected_connection: str | None = None) -> str:
    with locked():
        record = _read("connection")
        if not record or (expected_connection and record["connection_id"] != expected_connection):
            raise protocol.ChatGPTError("connection_changed", "Connect ChatGPT again and approve this request.")
        if record.get("health") == "blocked_usage":
            raise protocol.ChatGPTError("subscription_sharing_usage_limit_exceeded")
        if record.get("health") == "blocked_auth":
            raise protocol.ChatGPTError("authentication_required")
        credentials = record["credentials"]
        if float(credentials.get("expires_at", 0)) <= time.time() + 90:
            try:
                record["credentials"] = protocol.refresh_credentials(credentials)
            except protocol.ChatGPTError as exc:
                if exc.code in {"authentication_failed", "plan_permission_missing"}:
                    record["health"] = "blocked_auth"
                    _write("connection", record)
                raise
            _write("connection", record)
        return record["credentials"]["access_token"]


def refresh_models() -> dict:
    token = access_token()
    models = protocol.list_models(token)
    with locked():
        record = _read("connection")
        if record and record["credentials"]["access_token"] == token:
            record["models"] = models
            _write("connection", record)
    return {"models": models}


def mark_health(connection_id: str, health: str):
    with locked():
        record = _read("connection")
        if record and record["connection_id"] == connection_id:
            record["health"] = health
            _write("connection", record)


def unblock(owner_id: str):
    with locked():
        record = _read("connection")
        if not record or record["owner_id"] != owner_id:
            raise protocol.ChatGPTError("owner_required")
        if record.get("health") == "blocked_auth":
            raise protocol.ChatGPTError("authentication_required")
        record["health"] = "connected"
        _write("connection", record)


def disconnect() -> dict:
    confirmed = True
    with locked():
        record = _read("connection")
        if record:
            confirmed = False
            try:
                metadata = httpx.get(protocol.AUTH_ORIGIN + "/.well-known/openid-configuration", timeout=15).json()
                endpoint = metadata.get("revocation_endpoint", "")
                if endpoint.startswith(protocol.AUTH_ORIGIN + "/"):
                    for delay in (0, 1, 2):
                        if delay:
                            time.sleep(delay)
                        response = httpx.post(endpoint, data={"token": record["credentials"]["refresh_token"],
                                              "token_type_hint": "refresh_token", "client_id": record["credentials"]["client_id"]}, timeout=15)
                        if response.status_code == 200:
                            confirmed = True
                            break
                        if response.status_code < 500:
                            break
            except (httpx.HTTPError, ValueError, KeyError):
                pass
        for name in ("connection.enc", "setup.enc"):
            (_directory() / name).unlink(missing_ok=True)
    return {"connected": False, "revocation_confirmed": confirmed, "usage_url": USAGE_URL}


def request(model: str, text: str, image_url: str | None = None, *, connection_id: str,
            timeout: int = 600, check=None) -> dict:
    for attempt in range(3):
        try:
            return protocol.infer(access_token(connection_id), protocol.response_payload(model, text, image_url), timeout, check=check)
        except protocol.ChatGPTError as exc:
            if exc.code in {"subscription_sharing_usage_limit_exceeded", "usage_limited"}:
                mark_health(connection_id, "blocked_usage")
            elif exc.code in {"authentication_failed", "authentication_required", "subscription_sharing_invalid_user"}:
                mark_health(connection_id, "blocked_auth")
            if (exc.code not in {"subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"}
                    or getattr(exc, "partial_output", False) or attempt == 2):
                raise
            time.sleep(2 ** attempt)
    raise protocol.ChatGPTError("provider_error")
