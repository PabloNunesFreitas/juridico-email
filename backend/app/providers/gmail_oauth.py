"""
Helper CLI para obter o REFRESH TOKEN inicial do Gmail.

Uso:
    docker compose run --rm -p 8765:8765 backend python -m app.providers.gmail_oauth

Pré-requisitos no .env:
    GMAIL_CLIENT_ID=<seu>
    GMAIL_CLIENT_SECRET=<seu>

No Google Cloud Console o OAuth client deve ser do tipo "Web application"
com redirect URI = http://localhost:8765/callback

OU "Desktop app" — neste caso o redirect_uri padrão é
"urn:ietf:wg:oauth:2.0:oob" (mas Google deprecou isso); use Web application.
"""
import http.server
import socketserver
import threading
import urllib.parse
import webbrowser

import httpx

from app.core.config import settings


REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "https://www.googleapis.com/auth/gmail.readonly"
PORT = 8765


def _auth_url() -> str:
    params = {
        "client_id": settings.GMAIL_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "access_type": "offline",   # necessário pra receber refresh_token
        "prompt": "consent",        # força emitir refresh_token mesmo se já tiver consentido
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _exchange(code: str) -> dict:
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET:
        raise SystemExit("Configure GMAIL_CLIENT_ID e GMAIL_CLIENT_SECRET no .env primeiro.")

    captured: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a, **_kw):
            return

        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            captured["code"] = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Autorizado! Pode fechar esta janela." if captured["code"] else f"Falha: {params}"
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h2>{msg}</h2></body></html>".encode())

    url = _auth_url()
    print("\n=== Gmail OAuth — autorizacao inicial ===\n")
    print("Abra esta URL no navegador (se nao abrir sozinho):\n")
    print(url)
    print()

    server = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print(f"Aguardando callback em {REDIRECT_URI} ...")
    while "code" not in captured:
        pass

    code = captured["code"]
    if not code:
        raise SystemExit("Nao recebeu code do Google.")

    tokens = _exchange(code)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit(f"Resposta sem refresh_token (rode com prompt=consent): {tokens}")

    print("\n=== SUCESSO ===")
    print("Cole no seu .env:\n")
    print(f"GMAIL_REFRESH_TOKEN={refresh}\n")
    print("Depois reinicie o backend (docker compose up -d --force-recreate backend).")


if __name__ == "__main__":
    main()
