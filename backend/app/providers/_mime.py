"""Montagem de mensagens MIME compartilhada entre providers (IMAP, Gmail).

Centraliza a construção do e-mail para não duplicar a lógica de multipart entre
os providers e para dar suporte a imagens embutidas no corpo ("print no corpo"),
via referência cid: em um corpo HTML.
"""
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple

# attachments: (filename, mime_type, bytes)
Attachment = Tuple[str, str, bytes]
# inline_images: (filename, mime_type, bytes, cid)
InlineImage = Tuple[str, str, bytes, str]


def _attach_file(msg, filename: str, mime_type: str, data: bytes) -> None:
    main, _, sub = (mime_type or "application/octet-stream").partition("/")
    part = MIMEBase(main or "application", sub or "octet-stream")
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(part)


def _attach_inline(related, filename: str, mime_type: str, data: bytes, cid: str) -> None:
    main, _, sub = (mime_type or "image/png").partition("/")
    part = MIMEBase(main or "image", sub or "png")
    part.set_payload(data)
    encoders.encode_base64(part)
    # Content-ID entre <> é como o HTML referencia via src="cid:...".
    part.add_header("Content-ID", f"<{cid}>")
    part.add_header("Content-Disposition", "inline", filename=filename)
    related.attach(part)


def build_email_mime(
    *,
    from_addr: str,
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[List[str]] = None,
    attachments: Optional[List[Attachment]] = None,
    inline_images: Optional[List[InlineImage]] = None,
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
):
    """Monta a mensagem MIME.

    Sem body_html/inline_images e sem anexos -> text/plain simples (idêntico ao
    comportamento anterior). Com HTML/imagens embutidas monta:

        multipart/mixed
          multipart/related
            multipart/alternative -> text/plain + text/html
            <imagens inline (Content-ID)>
          <anexos comuns>
    """
    attachments = attachments or []
    inline_images = inline_images or []
    use_html = bool(body_html) or bool(inline_images)

    if not use_html and not attachments:
        root = MIMEText(body_text or "", "plain", "utf-8")
    elif not use_html:
        # texto puro + anexos comuns (comportamento anterior)
        root = MIMEMultipart("mixed")
        root.attach(MIMEText(body_text or "", "plain", "utf-8"))
        for fname, mtype, data in attachments:
            _attach_file(root, fname, mtype, data)
    else:
        # corpo HTML com imagens embutidas
        root = MIMEMultipart("mixed")

        related = MIMEMultipart("related")
        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body_text or "", "plain", "utf-8"))
        alternative.attach(MIMEText(body_html or "", "html", "utf-8"))
        related.attach(alternative)
        for fname, mtype, data, cid in inline_images:
            _attach_inline(related, fname, mtype, data, cid)
        root.attach(related)

        for fname, mtype, data in attachments:
            _attach_file(root, fname, mtype, data)

    root["From"] = from_addr
    root["To"] = to
    root["Subject"] = subject
    if cc:
        root["Cc"] = ", ".join(cc)
    # Cabeçalhos de encadeamento (threading) — fazem o Outlook/Gmail agruparem a
    # resposta na mesma conversa do e-mail original.
    if message_id:
        root["Message-ID"] = message_id
    if in_reply_to:
        root["In-Reply-To"] = in_reply_to
    if references:
        root["References"] = references
    return root
