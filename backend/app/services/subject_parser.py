"""
Parser do assunto padrão:
    Status / Nome do Cliente / NUP / Banco / Responsável

No PoC fazemos best-effort split por '/'. No MVP isso pode virar regex robusta.
"""
import re
from typing import Optional

from app.models.demand import Bank, DemandStatus

_BANK_MAP = {
    "bb": Bank.BB,
    "banco do brasil": Bank.BB,
    "cef": Bank.CEF,
    "caixa": Bank.CEF,
    "caixa econômica federal": Bank.CEF,
    "itau": Bank.ITAU,
    "itaú": Bank.ITAU,
    "bradesco": Bank.BRADESCO,
    "santander": Bank.SANTANDER,
}

_STATUS_KEYWORDS = {
    "solicita proposta": DemandStatus.SOLICITADA_PROPOSTA,
    "proposta aceita": DemandStatus.PROPOSTA_ACEITA,
    "enviar minuta assinada": DemandStatus.ENVIAR_MINUTA_ASSINADA,
    "minuta assinada": DemandStatus.MINUTA_ASSINADA,
    "follow up": DemandStatus.FOLLOW_UP,
    "pendências": DemandStatus.PENDENCIAS,
    "pendencias": DemandStatus.PENDENCIAS,
    "erro": DemandStatus.ERRO,
    "acordo realizado": DemandStatus.ACORDOS_REALIZADOS,
    "acordos realizados": DemandStatus.ACORDOS_REALIZADOS,
    "enviar resposta banco": DemandStatus.ENVIAR_RESPOSTA_BANCO,
    "proposta com erro": DemandStatus.PROPOSTA_COM_ERRO,
}


def normalize_subject(subject: Optional[str]) -> str:
    if not subject:
        return ""
    s = re.sub(r"^(re|fwd|fw|enc):\s*", "", subject.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def parse_subject(subject: Optional[str]) -> dict:
    """Tenta extrair status, cliente, nup, banco do assunto padrão."""
    out: dict = {}
    if not subject:
        return out
    parts = [p.strip() for p in subject.split("/")]
    if len(parts) >= 5:
        status_part, client_part, nup_part, bank_part, *_ = parts
        out["client_name"] = client_part or None
        out["nup"] = nup_part or None
        bank_key = bank_part.lower()
        for k, v in _BANK_MAP.items():
            if k in bank_key:
                out["bank"] = v
                break
        status_key = status_part.lower()
        for k, v in _STATUS_KEYWORDS.items():
            if k in status_key:
                out["status"] = v
                break
    return out
