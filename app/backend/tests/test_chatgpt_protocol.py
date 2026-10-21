import copy
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai import chatgpt_protocol as protocol


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.private, public = protocol.new_transfer_key()
        self.setup = dict(version=1, public_key=public, host_id="urn:uuid:server-one",
                          attempt_id="attempt-one", expires_at=time.time() + 60)
        self.credentials = dict(access_token="never-log-this", refresh_token="also-secret", client_id="issued-id")

    def test_only_target_server_can_open_connection(self):
        envelope = protocol.seal_connection(self.setup, self.credentials)
        self.assertNotIn("never-log-this", json.dumps(envelope))
        self.assertEqual(protocol.open_connection(self.setup, envelope, self.private), self.credentials)
        other_private, _ = protocol.new_transfer_key()
        with self.assertRaises(protocol.ChatGPTError):
            protocol.open_connection(self.setup, envelope, other_private)

    def test_rejects_tampering_wrong_host_and_wrong_attempt(self):
        envelope = protocol.seal_connection(self.setup, self.credentials)
        for field in ("ciphertext", "host_id", "attempt_id", "nonce", "public_key"):
            with self.subTest(field=field):
                changed = {**envelope, field: "invalid"}
                with self.assertRaises(protocol.ChatGPTError):
                    protocol.open_connection(self.setup, changed, self.private)

    def test_expired_setup_cannot_encrypt_or_decrypt(self):
        envelope = protocol.seal_connection(self.setup, self.credentials)
        self.setup["expires_at"] = time.time() - 1
        with self.assertRaises(protocol.ChatGPTError):
            protocol.seal_connection(self.setup, self.credentials)
        with self.assertRaises(protocol.ChatGPTError):
            protocol.open_connection(self.setup, envelope, self.private)


class OAuthTests(unittest.TestCase):
    def test_registration_and_reauthorization_use_pkce_and_app_identity(self):
        url, verifier, state = protocol.authorization_url("urn:uuid:host", "nonce", "http://127.0.0.1:1234/auth/callback")
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["agent_name_hint"], ["Knitting Library"])
        self.assertEqual(params["client_id"], ["dynamic_agent_client"])
        self.assertEqual(params["state"], [state])
        self.assertEqual(params["code_challenge"], [protocol.b64(protocol.hashlib.sha256(verifier.encode()).digest())])
        returning, _, _ = protocol.authorization_url("urn:uuid:host", "nonce", "http://127.0.0.1:1234/auth/callback", "issued-id")
        self.assertNotIn("agent_name_hint", parse_qs(urlsplit(returning).query))

    @patch.object(protocol, "validate_identity", return_value={"subject": "person"})
    @patch.object(protocol, "token_request")
    def test_identity_sign_in_alone_does_not_authorize_plan(self, token_request, _identity):
        token_request.return_value = dict(id_token="id", access_token="access", scope="openid profile email", refresh_token="refresh")
        with self.assertRaises(protocol.ChatGPTError) as caught:
            protocol.finish_sign_in("code", "issued-id", "verifier", "callback", "nonce")
        self.assertEqual(caught.exception.code, "plan_permission_missing")

    @patch.object(protocol, "token_request")
    def test_rotated_refresh_token_replaces_old_token_and_retains_identity(self, request):
        request.return_value = dict(access_token="new-access", refresh_token="new-refresh", expires_at=99)
        old = dict(client_id="issued-id", access_token="old-access", refresh_token="old-refresh",
                   scope=protocol.SCOPES, subject="person")
        new = protocol.refresh_credentials(old)
        self.assertEqual(new["subject"], "person")
        self.assertEqual(new["refresh_token"], "new-refresh")
        self.assertEqual(old["refresh_token"], "old-refresh")
        self.assertNotIn("scope", request.call_args.args[0])

    @patch.object(protocol.httpx, "post")
    def test_http_errors_never_expose_secret_response_body(self, post):
        post.return_value = Mock(status_code=401, text="access-token-secret")
        with self.assertRaises(protocol.ChatGPTError) as caught:
            protocol.token_request({})
        self.assertNotIn("access-token-secret", str(caught.exception))

    @patch.object(protocol.jwt, "decode")
    @patch.object(protocol.jwt, "PyJWKClient")
    @patch.object(protocol.httpx, "get")
    def test_nonce_and_identity_requirements_are_enforced(self, get, keys, decode):
        get.return_value.json.return_value = dict(jwks_uri=protocol.AUTH_ORIGIN + "/jwks", issuer=protocol.AUTH_ORIGIN)
        decode.return_value = dict(sub="person", iss=protocol.AUTH_ORIGIN, nonce="expected")
        self.assertEqual(protocol.validate_identity("id", "client", "expected")["subject"], "person")
        self.assertEqual(decode.call_args.kwargs["algorithms"], ["RS256"])
        self.assertEqual(decode.call_args.kwargs["audience"], "client")
        with self.assertRaises(protocol.ChatGPTError):
            protocol.validate_identity("id", "client", "wrong")


class StreamTests(unittest.TestCase):
    def test_image_payload_uses_supported_fields_only(self):
        payload = protocol.response_payload("model", "transcribe", "data:image/png;base64,AA")
        self.assertEqual(set(payload), {"model", "input", "store", "stream"})
        self.assertFalse(payload["store"])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["input"][0]["content"][1]["type"], "input_image")

    def test_only_completed_event_returns_text_and_normalized_usage(self):
        chunks = []
        self.assertIsNone(protocol.consume_event(dict(type="response.output_text.delta", delta="Recipe "), chunks))
        self.assertIsNone(protocol.consume_event(dict(type="response.output_text.delta", delta="text"), chunks))
        result = protocol.consume_event(dict(type="response.completed", response=dict(status="completed", usage=dict(input_tokens=4, output_tokens=2, total_tokens=6))), chunks)
        self.assertEqual(result, dict(text="Recipe text", usage=dict(prompt_tokens=4, completion_tokens=2, total_tokens=6)))

    def test_error_after_partial_output_is_not_success(self):
        chunks = ["partial result"]
        for event in (dict(type="response.incomplete"), dict(type="response.completed", response=dict(status="incomplete")),
                      dict(type="response.failed", response=dict(error=dict(code="subscription_sharing_usage_limit_exceeded")))):
            with self.subTest(event=event):
                with self.assertRaises(protocol.ChatGPTError):
                    protocol.consume_event(event, chunks)

    def test_untrusted_error_text_is_not_exposed(self):
        with self.assertRaises(protocol.ChatGPTError) as caught:
            protocol.consume_event(dict(type="error", error=dict(code="Bearer token/secret", message="secret")), [])
        self.assertEqual(caught.exception.code, "provider_error")


if __name__ == "__main__":
    unittest.main()
