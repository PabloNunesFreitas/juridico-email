"""
Helper CLI para obter o REFRESH TOKEN inicial do Outlook (modo delegated).

Uso:
    docker compose exec backend python -m app.providers.outlook_oauth

Pré-requisitos no .env (ou ambiente):
    OUTLOOK_CLIENT_ID=<seu>
    OUTLOOK_CLIENT_SECRET=<seu>
    # OUTLOOK_TENANT_ID pode ficar vazio (default: common)

Fluxo:
    1. Script imprime uma URL — abra no navegador.
    2. Logue com sua conta Outlook.com / Hotmail (ou corporativa).
    3. Autorize o acesso.
    4. Microsoft redireciona para http://localhost:8765/callback?code=...
    5. O script captura o code, troca por tokens, imprime o refresh_token.
    6. Cole no .env como OUTLOOK_REFRESH_TOKEN e reinicie o backend.

O refresh_token vale ~90 dias mas é renovado a cada uso, então na prática dura
indefinidamente enquanto o sistema sincroniza periodicamente.
"""
import http.server
import socketserver
import threading
import urllib.parse
import webbrowser

import httpx

from app.core.config import settings


REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "Mail.Read Mail.Send offline_access User.Read"
PORT = 8765


def _auth_url(tenant: str) -> str:
    params = {
        "client_id": settings.OUTLOOK_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": SCOPES,
        "prompt": "consent",
    }
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)


def _exchange(code: str, tenant: str) -> dict:
    resp = httpx.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": settings.OUTLOOK_CLIENT_ID,
            "client_secret": settings.OUTLOOK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if not settings.OUTLOOK_CLIENT_ID or not settings.OUTLOOK_CLIENT_SECRET:
        raise SystemExit("Configure OUTLOOK_CLIENT_ID e OUTLOOK_CLIENT_SECRET no .env primeiro.")

    tenant = settings.OUTLOOK_TENANT_ID or "common"
    captured: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a, **_kw):
            return

        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            code = params.get("code", [None])[0]
            captured["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Autorizado! Pode fechar esta janela." if code else f"Falha: {params}"
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h2>{msg}</h2></body></html>".encode())

    url = _auth_url(tenant)
    print("\n=== Outlook OAuth — autorização inicial ===\n")
    print("Abra esta URL no navegador (se não abrir sozinho):\n")
    print(url)
    print()

    server = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        webbrowser.open(url)
    except Exception:
        pass

    # Espera o redirect
    print(f"Aguardando callback em {REDIRECT_URI} ...")
    while "code" not in captured:
        pass

    code = captured["code"]
    if not code:
        raise SystemExit("Nao recebeu code do Microsoft.")

    tokens = _exchange(code, tenant)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit(f"Resposta sem refresh_token: {tokens}")

    print("\n=== SUCESSO ===")
    print("Cole no seu .env:\n")
    print(f"OUTLOOK_REFRESH_TOKEN={refresh}\n")
    print("Depois reinicie o backend (docker compose up -d --force-recreate backend).")


if __name__ == "__main__":
    main()
