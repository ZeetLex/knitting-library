"""Shared, standalone Sign in with ChatGPT protocol for the server and helper.

No application startup, database access, or credential logging on import.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUTH_ORIGIN = "https://auth.openai.com"
AUTHORIZE_URL = AUTH_ORIGIN + "/api/accounts/authorize"
TOKEN_URL = AUTH_ORIGIN + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"


class ChatGPTError(Exception):
    """Safe public error; never includes response bodies, tokens or OAuth URLs."""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def authorization_url(host_id: str, nonce: str, redirect_uri: str, client_id: str = "dynamic_agent_client") -> tuple[str, str, str]:
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    params = dict(client_id=client_id, ext_agent_host_id=host_id, response_type="code",
                  redirect_uri=redirect_uri, scope=SCOPES, resource=RESOURCE,
                  state=state, nonce=nonce, code_challenge_method="S256",
                  code_challenge=b64(hashlib.sha256(verifier.encode()).digest()))
    if client_id == "dynamic_agent_client":
        params["agent_name_hint"] = "Knitting Library"
    return AUTHORIZE_URL + "?" + urlencode(params), verifier, state


def token_request(values: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, data={**values, "resource": RESOURCE}, timeout=45)
        if response.status_code != 200:
            raise ChatGPTError("authentication_failed", "ChatGPT authentication failed. Sign in again.")
        result = response.json()
        if not result.get("access_token"):
            raise ChatGPTError("authentication_failed")
        result["expires_at"] = time.time() + int(result.get("expires_in", 3600))
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise ChatGPTError("connection_failed", "Could not reach ChatGPT authentication.") from None


def validate_identity(id_token: str, client_id: str, nonce: str | None = None) -> dict:
    try:
        metadata_response = httpx.get(AUTH_ORIGIN + "/.well-known/openid-configuration", timeout=30)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        # Never follow token-controlled URLs or accept another authorization server.
        jwks_url = metadata["jwks_uri"]
        if not jwks_url.startswith(AUTH_ORIGIN + "/"):
            raise ValueError("Unexpected issuer metadata")
        key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=client_id,
                            issuer=metadata["issuer"], options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise ValueError("Nonce mismatch")
        return {"subject": claims["sub"], "email": claims.get("email", ""), "issuer": claims["iss"]}
    except Exception:
        raise ChatGPTError("invalid_identity", "The ChatGPT identity could not be verified.") from None


def finish_sign_in(code: str, client_id: str, verifier: str, redirect_uri: str, nonce: str) -> dict:
    if not client_id or client_id == "dynamic_agent_client":
        raise ChatGPTError("invalid_registration", "OpenAI did not issue an app registration.")
    tokens = token_request(dict(grant_type="authorization_code", client_id=client_id,
                               code=code, code_verifier=verifier, redirect_uri=redirect_uri))
    identity = validate_identity(tokens.get("id_token", ""), client_id, nonce)
    if PLAN_SCOPE not in tokens.get("scope", "").split():
        raise ChatGPTError("plan_permission_missing", "Sign-in succeeded, but ChatGPT plan usage was not authorized.")
    if not tokens.get("refresh_token"):
        raise ChatGPTError("refresh_permission_missing", "Renewable access was not granted.")
    return {**tokens, **identity, "client_id": client_id}


def refresh_credentials(credentials: dict) -> dict:
    replacement = token_request(dict(grant_type="refresh_token", client_id=credentials["client_id"],
                                     refresh_token=credentials["refresh_token"]))
    scopes = replacement.get("scope", credentials.get("scope", ""))
    if PLAN_SCOPE not in scopes.split():
        raise ChatGPTError("plan_permission_missing")
    return {**credentials, **replacement, "scope": scopes}


def list_models(access_token: str) -> list[dict]:
    try:
        response = httpx.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + access_token}, timeout=45)
        if response.status_code != 200:
            raise ChatGPTError("model_access_failed", "Could not load models for the connected ChatGPT account.")
        return [{"id": item["slug"], "name": item.get("display_name", item["slug"])}
                for item in response.json().get("models", [])
                if item.get("visibility") == "list" and item.get("slug")]
    except (httpx.HTTPError, ValueError, KeyError):
        raise ChatGPTError("model_access_failed") from None


def response_payload(model: str, text: str, image_url: str | None = None) -> dict:
    content = [{"type": "input_text", "text": text}]
    if image_url:
        content.append({"type": "input_image", "image_url": image_url})
    return {"model": model, "store": False, "stream": True,
            "input": [{"role": "user", "content": content}]}


def consume_event(event: dict, chunks: list[str]) -> dict | None:
    kind = event.get("type")
    if kind == "response.output_text.delta":
        chunks.append(event.get("delta", ""))
    elif kind == "response.completed":
        response = event.get("response", {})
        if response.get("status") != "completed":
            raise ChatGPTError("incomplete_response", "ChatGPT did not complete the page.")
        usage = response.get("usage", {})
        return {"text": "".join(chunks), "usage": {"prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0), "total_tokens": usage.get("total_tokens", 0)}}
    elif kind in {"response.failed", "response.incomplete", "error"}:
        code = event.get("error", event.get("response", {}).get("error") or {}).get("code", "incomplete_response")
        # Only expose a bounded identifier, never arbitrary provider text.
        if not isinstance(code, str) or not code.replace("_", "").isalnum() or len(code) > 100:
            code = "provider_error"
        raise ChatGPTError(code)
    return None


def infer(access_token: str, payload: dict, timeout: int = 600) -> dict:
    chunks: list[str] = []
    try:
        with httpx.stream("POST", RESOURCE + "/responses", json=payload,
                          headers={"Authorization": "Bearer " + access_token}, timeout=timeout) as response:
            if response.status_code != 200:
                response.read()
                try:
                    error = response.json().get("error") or {}
                    consume_event({"type": "error", "error": error}, chunks)
                except ValueError:
                    pass
                raise ChatGPTError("provider_error")
            for line in response.iter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    result = consume_event(json.loads(line[6:]), chunks)
                    if result is not None:
                        return result
    except (httpx.HTTPError, ValueError):
        raise ChatGPTError("connection_failed", "The ChatGPT request was interrupted.") from None
    raise ChatGPTError("incomplete_response", "ChatGPT ended the stream before completing the page.")


def new_transfer_key() -> tuple[str, str]:
    key = X25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return b64(private), b64(public)


def _transfer_key(private: X25519PrivateKey, public: X25519PublicKey, attempt_id: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=("knitting-chatgpt-v1:" + attempt_id).encode()).derive(private.exchange(public))


def seal_connection(setup: dict, credentials: dict) -> dict:
    if setup.get("version") != 1 or float(setup.get("expires_at", 0)) < time.time():
        raise ChatGPTError("setup_expired", "Download a new setup package from AI settings.")
    ephemeral = X25519PrivateKey.generate()
    key = _transfer_key(ephemeral, X25519PublicKey.from_public_bytes(unb64(setup["public_key"])), setup["attempt_id"])
    nonce = secrets.token_bytes(12)
    aad = (setup["attempt_id"] + ":" + setup["host_id"]).encode()
    ciphertext = AESGCM(key).encrypt(nonce, json.dumps(credentials).encode(), aad)
    return {"version": 1, "attempt_id": setup["attempt_id"], "host_id": setup["host_id"],
            "public_key": b64(ephemeral.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)),
            "nonce": b64(nonce), "ciphertext": b64(ciphertext)}


def open_connection(setup: dict, envelope: dict, private_key: str) -> dict:
    try:
        if setup["expires_at"] < time.time():
            raise ValueError("Expired")
        if any(envelope.get(k) != setup[k] for k in ("version", "attempt_id", "host_id")):
            raise ValueError("Wrong setup")
        private = X25519PrivateKey.from_private_bytes(unb64(private_key))
        key = _transfer_key(private, X25519PublicKey.from_public_bytes(unb64(envelope["public_key"])), setup["attempt_id"])
        aad = (setup["attempt_id"] + ":" + setup["host_id"]).encode()
        return json.loads(AESGCM(key).decrypt(unb64(envelope["nonce"]), unb64(envelope["ciphertext"]), aad))
    except Exception:
        raise ChatGPTError("invalid_connection_file", "The connection file is invalid, expired, or belongs to another server.") from None
