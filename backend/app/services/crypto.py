"""Symmetric encryption for aggregator access tokens at rest.

Dev-shaped placeholder: a Fernet key from an env var. Before this touches
real bank data, TOKEN_ENCRYPTION_KEY should come from a secrets manager (AWS
Secrets Manager / GCP Secret Manager / etc.), not a plain env var.
"""

from cryptography.fernet import Fernet

from app.config import settings

_fernet = Fernet(settings.token_encryption_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
