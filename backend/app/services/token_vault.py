"""
Token Vault service — encrypts and decrypts OAuth tokens before persistence.
Never returns raw tokens in logs or API responses.
"""

from __future__ import annotations

from app.core.security import decrypt_token, encrypt_token


class TokenVault:
    """
    Provides a clean interface for storing and retrieving OAuth tokens.
    All tokens are Fernet-encrypted before hitting the database.
    """

    @staticmethod
    def store(plaintext_token: str) -> str:
        """Encrypt a token for database storage."""
        return encrypt_token(plaintext_token)

    @staticmethod
    def retrieve(encrypted_token: str) -> str:
        """Decrypt a token retrieved from the database."""
        return decrypt_token(encrypted_token)

    @staticmethod
    def safe_store(token: str | None) -> str | None:
        """Encrypt a token if not None."""
        if token is None:
            return None
        return encrypt_token(token)

    @staticmethod
    def safe_retrieve(encrypted: str | None) -> str | None:
        """Decrypt a token if not None."""
        if encrypted is None:
            return None
        return decrypt_token(encrypted)


token_vault = TokenVault()
