import hashlib
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from webauthn.helpers import bytes_to_base64url

from app.core.security import settings
from app.models import User, WebAuthnChallenge, WebAuthnCredential, utcnow
from tests.conftest import PASSWORD

ORIGIN = "http://localhost:5173"
BASE = "/api/v1/auth/passkeys"


@pytest.mark.parametrize(
    "credential",
    [
        {},
        {"id": [], "response": {}},
        {"id": "fixture", "response": []},
        {"id": "fixture", "response": {"clientDataJSON": None}},
    ],
)
def test_malformed_browser_responses_consume_challenges_without_server_errors(
    client, tokens, credential
):
    start = client.post(
        BASE + "/register/options", headers=tokens["admin"], json={"password": PASSWORD}
    ).json()
    body = {"challenge_id": start["challenge_id"], "credential": credential}
    assert (
        client.post(BASE + "/register/verify", headers=tokens["admin"], json=body).status_code
        == 400
    )
    assert (
        client.post(BASE + "/register/verify", headers=tokens["admin"], json=body).status_code
        == 401
    )


def test_concurrent_assertion_consumes_challenge_once_on_postgres(client, tokens, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent row locking requires PostgreSQL")
    authenticator, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200
    start = start_login(client).json()
    payload = {
        "challenge_id": start["challenge_id"],
        "credential": authenticator.response(start["options"]),
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: client.post(BASE + "/login/verify", json=payload), range(2))
        )
    assert sorted(response.status_code for response in responses) == [200, 401]


class Authenticator:
    """Synthetic software authenticator; signatures are verified by the real library."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.identifier = secrets.token_bytes(32)
        self.handle = None

    def response(
        self,
        options,
        *,
        register=False,
        counter=1,
        origin=ORIGIN,
        rp="localhost",
        uv=True,
        cross=False,
    ):
        client = json.dumps(
            {
                "type": "webauthn.create" if register else "webauthn.get",
                "challenge": options["challenge"],
                "origin": origin,
                "crossOrigin": cross,
            }
        ).encode()
        flags = 1 | (4 if uv else 0) | (64 if register else 0)
        auth = hashlib.sha256(rp.encode()).digest() + bytes([flags]) + counter.to_bytes(4, "big")
        response = {"clientDataJSON": bytes_to_base64url(client)}
        if register:
            public = self.key.public_key().public_numbers()
            cose = cbor2.dumps(
                {
                    1: 2,
                    3: -7,
                    -1: 1,
                    -2: public.x.to_bytes(32, "big"),
                    -3: public.y.to_bytes(32, "big"),
                }
            )
            auth += b"\0" * 16 + len(self.identifier).to_bytes(2, "big") + self.identifier + cose
            response["attestationObject"] = bytes_to_base64url(
                cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
            )
            response["transports"] = ["internal"]
            self.handle = options["user"]["id"]
        else:
            response.update(
                {
                    "authenticatorData": bytes_to_base64url(auth),
                    "signature": bytes_to_base64url(
                        self.key.sign(
                            auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256())
                        )
                    ),
                    "userHandle": self.handle,
                }
            )
        identifier = bytes_to_base64url(self.identifier)
        return {
            "id": identifier,
            "rawId": identifier,
            "type": "public-key",
            "response": response,
            "clientExtensionResults": {},
        }


def enroll(client, tokens, authenticator=None, **changes):
    authenticator = authenticator or Authenticator()
    start = client.post(
        BASE + "/register/options", headers=tokens["admin"], json={"password": PASSWORD}
    )
    assert start.status_code == 200, start.text
    start = start.json()
    credential = authenticator.response(start["options"], register=True, counter=0, **changes)
    finish = client.post(
        BASE + "/register/verify",
        headers=tokens["admin"],
        json={
            "challenge_id": start["challenge_id"],
            "credential": credential,
            "name": "Fixture device",
        },
    )
    return authenticator, finish, start, credential


def start_login(client):
    return client.post(
        BASE + "/login/options", json={"email": "admin@sentinelx.dev", "password": PASSWORD}
    )


def test_real_registration_and_assertion_revoke_old_sessions(client, tokens, db):
    authenticator, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200, finish.text
    assert len(finish.json()["recovery_codes"]) == 10
    assert client.get("/api/v1/dashboard", headers=tokens["admin"]).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "admin@sentinelx.dev", "password": PASSWORD}
        ).status_code
        == 401
    )
    start = start_login(client).json()
    assert start["options"]["userVerification"] == "required"
    credential = authenticator.response(start["options"])
    payload = {"challenge_id": start["challenge_id"], "credential": credential}
    finish = client.post(BASE + "/login/verify", json=payload)
    assert finish.status_code == 200, finish.text
    assert finish.json()["user"]["passkey_count"] == 1 and finish.json()["user"]["mfa_enabled"]
    headers = {"Authorization": "Bearer " + finish.json()["access_token"]}
    assert client.get("/api/v1/dashboard", headers=headers).status_code == 200
    assert client.post(BASE + "/login/verify", json=payload).status_code == 401
    listing = client.get(BASE, headers=headers).json()
    assert listing["items"][0]["name"] == "Fixture device"
    assert "public_key" not in json.dumps(listing) and "credential_id" not in json.dumps(listing)
    assert db.scalar(select(WebAuthnCredential)).sign_count == 1
    assert (
        client.post(
            BASE + f"/{listing['items'][0]['id']}/remove",
            headers=headers,
            json={"password": PASSWORD},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes",
    [{"origin": "https://evil.example"}, {"rp": "evil.example"}, {"uv": False}, {"cross": True}],
)
def test_registration_rejects_invalid_browser_properties(client, tokens, db, changes):
    _, finish, start, credential = enroll(client, tokens, **changes)
    assert finish.status_code == 400
    assert db.scalar(select(WebAuthnCredential)) is None
    assert (
        client.post(
            BASE + "/register/verify",
            headers=tokens["admin"],
            json={"challenge_id": start["challenge_id"], "credential": credential},
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "changes",
    [{"origin": "https://evil.example"}, {"rp": "evil.example"}, {"uv": False}, {"cross": True}],
)
def test_assertion_rejects_invalid_browser_properties(client, tokens, changes):
    authenticator, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200
    start = start_login(client).json()
    response = client.post(
        BASE + "/login/verify",
        json={
            "challenge_id": start["challenge_id"],
            "credential": authenticator.response(start["options"], **changes),
        },
    )
    assert response.status_code == 401


def test_wrong_signature_counter_and_account_handle_are_rejected(client, tokens):
    authenticator, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200
    other = Authenticator()
    start = start_login(client).json()
    invalid = authenticator.response(start["options"])
    invalid["response"]["signature"] = other.response(start["options"])["response"]["signature"]
    assert (
        client.post(
            BASE + "/login/verify",
            json={"challenge_id": start["challenge_id"], "credential": invalid},
        ).status_code
        == 401
    )
    start = start_login(client).json()
    invalid = authenticator.response(start["options"])
    invalid["response"]["userHandle"] = bytes_to_base64url(b"another-account")
    assert (
        client.post(
            BASE + "/login/verify",
            json={"challenge_id": start["challenge_id"], "credential": invalid},
        ).status_code
        == 401
    )
    start = start_login(client).json()
    assert (
        client.post(
            BASE + "/login/verify",
            json={
                "challenge_id": start["challenge_id"],
                "credential": authenticator.response(start["options"], counter=2),
            },
        ).status_code
        == 200
    )
    start = start_login(client).json()
    assert (
        client.post(
            BASE + "/login/verify",
            json={
                "challenge_id": start["challenge_id"],
                "credential": authenticator.response(start["options"], counter=2),
            },
        ).status_code
        == 401
    )


def test_challenges_are_expiring_version_bound_and_not_cross_account(client, tokens, db):
    auth, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200
    start = start_login(client).json()
    row = db.get(WebAuthnChallenge, start["challenge_id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            BASE + "/login/verify",
            json={
                "challenge_id": start["challenge_id"],
                "credential": auth.response(start["options"]),
            },
        ).status_code
        == 401
    )
    start = start_login(client).json()
    user = db.scalar(select(User).where(User.email == "admin@sentinelx.dev"))
    user.auth_version += 1
    db.commit()
    assert (
        client.post(
            BASE + "/login/verify",
            json={
                "challenge_id": start["challenge_id"],
                "credential": auth.response(start["options"]),
            },
        ).status_code
        == 401
    )
    user.disabled = True
    db.commit()
    assert start_login(client).status_code == 401


def test_passkey_recovery_is_single_use_and_production_gates_accept_verified_factor(
    client, tokens, monkeypatch
):
    monkeypatch.setattr(settings, "environment", "production")
    auth, finish, _, _ = enroll(client, tokens)
    assert finish.status_code == 200
    code = finish.json()["recovery_codes"][0]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sentinelx.dev", "password": PASSWORD, "otp": code},
    )
    assert response.status_code == 200
    assert (
        client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer " + response.json()["access_token"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@sentinelx.dev", "password": PASSWORD, "otp": code},
        ).status_code
        == 401
    )


def test_starter_password_and_foreign_origins_cannot_enroll(client, tokens, db):
    user = db.scalar(select(User).where(User.role == "ADMIN"))
    user.must_change_password = True
    db.commit()
    assert (
        client.post(
            BASE + "/register/options", headers=tokens["admin"], json={"password": PASSWORD}
        ).status_code
        == 403
    )
    user.must_change_password = False
    db.commit()
    assert (
        client.post(
            BASE + "/register/options",
            headers={**tokens["admin"], "Origin": "https://evil.example"},
            json={"password": PASSWORD},
        ).status_code
        == 403
    )
