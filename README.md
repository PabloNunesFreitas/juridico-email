# Gestão de E-mails Jurídicos — PoC

Sistema interno para transformar a gestão manual de e-mails relacionados a acordos
de processos de poupança em uma plataforma com controle de usuários, atribuição de
responsáveis, rastreabilidade e integração com Outlook/Gmail.

## Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic v2
- **Banco:** PostgreSQL 16
- **Auth:** JWT (HS256, password hash com bcrypt)
- **Frontend:** Next.js 14 (App Router) + TypeScript + TailwindCSS
- **Migrations:** Alembic (configurado; PoC também cria via `Base.metadata.create_all` na primeira subida)
- **Container:** Docker + Docker Compose

## Estrutura

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/          # endpoints REST
│   │   ├── core/            # config, db, security, deps
│   │   ├── models/          # SQLAlchemy
│   │   ├── schemas/         # Pydantic
│   │   ├── services/        # regras de negócio
│   │   ├── providers/       # EmailProvider + Outlook/Mock
│   │   ├── seeds.py         # admin inicial
│   │   └── main.py
│   ├── alembic/             # migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/                 # Next.js App Router
│   │   ├── login/
│   │   └── (app)/           # área autenticada
│   ├── components/
│   ├── lib/api.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Subir o projeto

```bash
cp .env.example .env
docker compose up --build
```

- Backend: http://localhost:8001 (Swagger em `/docs`)
- Frontend: http://localhost:3001
- Postgres exposto em `localhost:5433` (as portas 3000/5432 já são usadas por outra stack local — os containers internamente continuam usando 3000/8000/5432)

### Login inicial (seed)

- **E-mail:** `admin@empresa.com.br`
- **Senha:** `admin123`

> Configure `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` no `.env` antes do primeiro `up`.

## Provedor de e-mail

A camada de integração é abstrata (`app/providers/email_provider.py`). Implementações:

- **MockEmailProvider** (default) — gera e-mails sintéticos do fluxo jurídico de poupança
  com remetente, NUP, banco e status no assunto. Útil para validar o fluxo end-to-end
  antes das credenciais reais.
- **OutlookEmailProvider** — pronto para Microsoft Graph (`/users/{central}/messages`).
  Ative com `EMAIL_PROVIDER=outlook` e preencha `OUTLOOK_*` no `.env`.
- **Gmail** — slot reservado, basta criar `GmailEmailProvider` herdando de `EmailProvider`
  e plugar em `providers/__init__.py`.

A factory `get_email_provider()` resolve qual implementação usar pela env var `EMAIL_PROVIDER`.

## Fluxo principal (PoC)

1. Admin clica em **Sincronizar e-mails** no Dashboard.
2. Backend (`email_sync_service.sync_inbox`):
   - busca mensagens do provider;
   - identifica demanda existente por `thread_id` (ou `sender + normalized_subject`);
   - se nova: aplica continuidade automática via `assignment_rules` e tenta extrair
     `cliente / NUP / banco / status` do assunto padrão;
   - faz upsert idempotente da mensagem (chave: `external_message_id`);
   - registra logs para cada evento.
3. Admin atribui demanda → `PATCH /demands/{id}/assign` → cria `assignment_rule` para o remetente.
4. Próximas mensagens do mesmo remetente são **automaticamente** atribuídas ao mesmo responsável.
5. Usuário acessa **Minhas Solicitações** ou pega uma livre via **Assumir**.

## Modelagem do banco

Tabelas principais (ver `app/models/`):

- `users` (id, name, email, password_hash, role: ADMIN/USER, active)
- `email_accounts` (provider, email_address, access_token, refresh_token, active)
- `demands` (sender_email, external_thread_id, subject, normalized_subject, client_name, nup, bank, status, assigned_user_id, last_message_at)
- `messages` (demand_id, external_message_id, direction, body_text/html, received_at, has_attachments)
- `attachments` (message_id, filename, mime_type, size, external_attachment_id)
- `assignment_rules` (sender_email UNIQUE, assigned_user_id) — continuidade automática
- `audit_logs` (event_type, description, user_id, demand_id, metadata_json)

## Endpoints (resumo)

| Método | Rota | Quem |
|---|---|---|
| POST | `/api/v1/auth/login` | público |
| GET  | `/api/v1/auth/me` | autenticado |
| GET/POST/PATCH/DELETE | `/api/v1/users` | admin (POST/PATCH/DELETE) |
| POST | `/api/v1/email/sync` | admin |
| GET  | `/api/v1/email/messages` | autenticado |
| GET  | `/api/v1/demands` | autenticado (admin vê tudo) |
| GET  | `/api/v1/demands/my` | autenticado |
| GET  | `/api/v1/demands/unassigned` | autenticado |
| GET  | `/api/v1/demands/{id}` | autenticado (com check) |
| PATCH | `/api/v1/demands/{id}/assign` | admin |
| POST | `/api/v1/demands/{id}/assume` | autenticado |
| PATCH | `/api/v1/demands/{id}/status` | autenticado (responsável ou admin) |
| GET  | `/api/v1/logs` | admin |
| GET  | `/api/v1/demands/{id}/logs` | autenticado (com check) |
| GET/POST | `/api/v1/settings/email-provider` | admin |

## Eventos logados (auditoria)

`DEMAND_CREATED`, `DEMAND_ASSIGNED`, `DEMAND_AUTO_ASSIGNED`, `DEMAND_ASSUMED`,
`DEMAND_STATUS_CHANGED`, `MESSAGE_RECEIVED`, `USER_CREATED`, `USER_UPDATED`,
`USER_DEACTIVATED`, `SYNC_COMPLETED`, `SYNC_ERROR`.

## Status (espelhando o manual interno)

`Caixa de Entrada`, `Enviar resposta banco`, `Enviar minuta assinada`, `Pendências`,
`Erro`, `Acordos realizados`, `Solicitada proposta`, `Proposta aceita`, `Follow up`,
`Proposta com erro`, `Minuta assinada`.

Bancos: BB, CEF, Itaú, Bradesco, Santander, Outros.

## Migrations (Alembic)

Para gerar a primeira migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "init"
docker compose exec backend alembic upgrade head
```

> No PoC o startup também executa `Base.metadata.create_all`, então não é obrigatório
> rodar migrations para começar a usar. No MVP, remover o create_all e usar somente Alembic.

## O que NÃO está no PoC (por escopo)

IA de classificação, integração com Legalone, envio real de e-mails, movimentação de
pastas no Outlook/Gmail, OCR de anexos, dashboard avançado, multitenant. A arquitetura
(EmailProvider, services, audit_logs) já está preparada para esses incrementos.

## Roadmap

- **Bloco A — PoC funcional** ✅ entregue aqui
- **Bloco B — MVP utilizável:** filtros avançados, anexos persistidos, refinamento de permissões, parsing automático mais robusto, Celery para sync periódica.
- **Bloco C — Evolução:** envio de respostas pelo sistema, integração Legalone, sugestões via IA, notificações.

## Desenvolvimento sem Docker

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # ou .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/juridico
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```
