"""
attachment_storage.py — armazenamento local de anexos.

Responsabilidade única: salvar bytes de um anexo em disco e retornar o
caminho relativo; ou ler bytes de um caminho relativo já salvo.

Estrutura de diretórios:
    /opt/juridico-email/attachments/
        {account_id}/
            {message_external_id}/
                {att_id}_{filename_sanitizado}

Por que relativo no banco?  Permite mover o volume sem reescrever todos
os registros — apenas ajuste ATTACHMENT_ROOT no ambiente.
"""
import hashlib
import logging
import os
import re

log = logging.getLogger("attachment_storage")

# Pode ser sobrescrito via variável de ambiente ATTACHMENT_ROOT.
# Padrão compatível com Docker volume em produção.
ATTACHMENT_ROOT = os.environ.get(
    "ATTACHMENT_ROOT", "/opt/juridico-email/attachments"
)


def _safe_filename(name: str) -> str:
    """Remove caracteres não seguros para sistemas de arquivos."""
    name = re.sub(r"[^\w\.\-]", "_", name)
    return name[:180] or "attachment"


def _relative_path(
    account_id: int,
    message_external_id: str,
    att_db_id: int,
    filename: str,
) -> str:
    """Retorna caminho relativo (sem ATTACHMENT_ROOT)."""
    # Usa hash curto do message_external_id para evitar nomes gigantes
    # no filesystem (IDs do Gmail/Outlook são longos).
    msg_hash = hashlib.sha1(message_external_id.encode()).hexdigest()[:16]
    safe = _safe_filename(filename)
    return os.path.join(str(account_id), msg_hash, f"{att_db_id}_{safe}")


def full_path(relative: str) -> str:
    """Retorna caminho absoluto dado o relativo guardado no banco."""
    return os.path.join(ATTACHMENT_ROOT, relative)


def save(
    data: bytes,
    account_id: int,
    message_external_id: str,
    att_db_id: int,
    filename: str,
) -> str:
    """
    Persiste `data` em disco.

    Retorna o caminho **relativo** para guardar em Attachment.storage_path.
    Lança OSError se não conseguir escrever (espaço, permissão etc.).
    """
    rel = _relative_path(account_id, message_external_id, att_db_id, filename)
    abs_path = full_path(rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    # Escrita atômica: grava em tmp e move, evita arquivo corrompido em caso
    # de crash no meio da escrita.
    tmp_path = abs_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, abs_path)
    log.debug("Anexo salvo: %s (%d bytes)", rel, len(data))
    return rel


def load(relative: str) -> bytes:
    """
    Lê bytes do disco dado o caminho relativo.

    Lança FileNotFoundError se o arquivo não existir.
    """
    abs_path = full_path(relative)
    with open(abs_path, "rb") as f:
        return f.read()


def exists(relative: str) -> bool:
    """True se o arquivo físico estiver presente."""
    return os.path.isfile(full_path(relative))
