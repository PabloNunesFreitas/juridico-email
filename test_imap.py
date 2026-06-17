#!/usr/bin/env python3
"""Teste rápido do provider IMAP com mail.shared.acl.com.br"""
import sys
sys.path.insert(0, '/home/pablo/Área de trabalho/programa site e-mail/backend')

from app.providers.imap_provider import IMAPEmailProvider

# Configuração
IMAP_HOST = "mail.shared.acl.com.br"
IMAP_PORT = 993
SMTP_HOST = "mail.shared.acl.com.br"
SMTP_PORT = 587
EMAIL = "root@prevmasa.com.br"
PASSWORD = input("Digite a senha para root@prevmasa.com.br: ")

print(f"\n🧪 Testando conexão IMAP/SMTP em {IMAP_HOST}...")

try:
    provider = IMAPEmailProvider(
        imap_host=IMAP_HOST,
        imap_port=IMAP_PORT,
        smtp_host=SMTP_HOST,
        smtp_port=SMTP_PORT,
        email=EMAIL,
        password=PASSWORD,
        use_ssl_imap=True,
        use_tls_smtp=True,
    )

    print(f"✅ Conexão IMAP estabelecida")

    print(f"\n📧 Listando IDs de e-mails...")
    message_ids = provider.list_message_ids(limit=10)
    print(f"✅ Encontrados {len(message_ids)} e-mails")

    if message_ids:
        print(f"\n📬 Buscando detalhes do primeiro e-mail...")
        msg = provider.get_message_by_id(message_ids[0])
        if msg:
            print(f"  De: {msg.sender_email}")
            print(f"  Para: {msg.recipients}")
            print(f"  Assunto: {msg.subject}")
            print(f"  Recebido em: {msg.received_at}")
            print(f"  Anexos: {len(msg.attachments)}")
            print(f"✅ E-mail lido com sucesso")
        else:
            print(f"❌ Erro ao ler e-mail")

    print(f"\n✅ Teste concluído com sucesso!")

except Exception as e:
    print(f"\n❌ Erro: {e}")
    import traceback
    traceback.print_exc()
