"""Criptografia simétrica para senhas IMAP/SMTP."""
import base64
from cryptography.fernet import Fernet

from app.core.config import settings

# Gera chave a partir do JWT_SECRET
_key = base64.urlsafe_b64encode(settings.JWT_SECRET.encode()[:32].ljust(32, b'0'))
_cipher = Fernet(_key)


def encrypt_password(password: str) -> str:
    """Criptografa uma senha."""
    return _cipher.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Descriptografa uma senha."""
    return _cipher.decrypt(encrypted.encode()).decode()
