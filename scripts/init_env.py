"""Generate development secrets without overwriting an existing .env."""

import os
import base64
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
template = (root / ".env.example").read_text()
values = {
    "JWT_SECRET": secrets.token_urlsafe(48),
    "MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    "REDIS_PASSWORD": secrets.token_urlsafe(24),
    "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(18),
}
for key, value in values.items():
    template = template.replace(f"{key}=\n", f"{key}={value}\n")
try:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; it was not changed.") from None
with os.fdopen(descriptor, "w") as file:
    file.write(template)
print(f"Created {path} with random development secrets (permissions 0600).")
print("Sign in as admin@sentinelx.dev using BOOTSTRAP_ADMIN_PASSWORD from .env.")
