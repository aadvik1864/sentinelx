"""Encrypted TOTP enrollment and atomic, single-use verification.

The caller must lock the user row before verification and commit consumption.
Recovery credentials have 128 bits of entropy and are stored only as digests.
"""

import hmac
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import token_digest


def cipher():
    key = get_settings().mfa_encryption_key
    if not key:
        raise HTTPException(
            503, "Authenticator encryption is not configured. Contact the server administrator."
        )
    return Fernet(key.encode())


def encrypt(secret: str) -> str:
    return cipher().encrypt(secret.encode()).decode()


def decrypt(secret: str) -> str:
    try:
        return cipher().decrypt(secret.encode()).decode()
    except InvalidToken:
        raise HTTPException(
            503, "Authenticator key unavailable. Contact the server administrator."
        ) from None


def verify(user, code: str) -> bool:
    if user.mfa_secret and len(code) == 6 and code.isascii() and code.isdigit():
        totp = pyotp.TOTP(decrypt(user.mfa_secret))
        step = int(time.time()) // totp.interval
        for candidate in (step, step - 1, step + 1):
            if candidate > user.mfa_last_step and hmac.compare_digest(
                totp.at(candidate * totp.interval), code
            ):
                user.mfa_last_step = candidate
                return True
        return False
    digest = token_digest(code)
    for stored in user.mfa_recovery_hashes:
        if hmac.compare_digest(stored, digest):
            user.mfa_recovery_hashes = [
                value for value in user.mfa_recovery_hashes if value != stored
            ]
            return True
    return False


def recovery_codes(user) -> list[str]:
    codes = [secrets.token_hex(16) for _ in range(10)]
    user.mfa_recovery_hashes = [token_digest(code) for code in codes]
    return codes
