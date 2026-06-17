#!/usr/bin/env python3
"""Teste simples do provider IMAP sem dependências de Django"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Importar apenas o que precisamos
import imaplib
import smtplib
from datetime import datetime, timezone

IMAP_HOST = "mail.shared.acl.com.br"
IMAP_PORT = 993
SMTP_HOST = "mail.shared.acl.com.br"
SMTP_PORT = 587
EMAIL = "root@prevmasa.com.br"
PASSWORD = input(f"\nDigite a senha para {EMAIL}: ")

print(f"\n🧪 Teste IMAP/SMTP: {IMAP_HOST}")
print("=" * 60)

# Teste IMAP
print(f"\n📧 Conectando IMAP (SSL/TLS porta {IMAP_PORT})...")
try:
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    print(f"✅ Conexão IMAP: OK")

    print(f"\n🔑 Autenticando...")
    imap.login(EMAIL, PASSWORD)
    print(f"✅ Autenticação IMAP: OK")

    print(f"\n📬 Selecionando INBOX...")
    status, mailbox_info = imap.select("INBOX")
    if status == "OK":
        num_emails = int(mailbox_info[0])
        print(f"✅ INBOX: {num_emails} e-mails")

    print(f"\n📋 Listando últimos 5 e-mails...")
    status, message_ids = imap.search(None, "ALL")
    if status == "OK":
        ids = message_ids[0].split()[-5:]
        print(f"✅ Encontrados IDs: {[mid.decode() for mid in ids]}")

        if ids:
            print(f"\n📖 Lendo primeiro e-mail...")
            status, data = imap.fetch(ids[0], "(RFC822)")
            if status == "OK":
                print(f"✅ E-mail baixado: {len(data[0][1])} bytes")

    imap.close()
    print(f"\n✅ IMAP desconectado")

except Exception as e:
    print(f"\n❌ Erro IMAP: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Teste SMTP
print(f"\n📧 Conectando SMTP (STARTTLS porta {SMTP_PORT})...")
try:
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    print(f"✅ Conexão SMTP: OK")

    print(f"\n🔐 Iniciando TLS...")
    smtp.starttls()
    print(f"✅ TLS: OK")

    print(f"\n🔑 Autenticando...")
    smtp.login(EMAIL, PASSWORD)
    print(f"✅ Autenticação SMTP: OK")

    smtp.quit()
    print(f"\n✅ SMTP desconectado")

except Exception as e:
    print(f"\n❌ Erro SMTP: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n" + "=" * 60)
print(f"✅ TODOS OS TESTES PASSARAM!")
print(f"✅ O servidor mail.shared.acl.com.br está acessível")
print(f"✅ Credenciais estão corretas")
