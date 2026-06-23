from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Juridico Email Manager"
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/juridico"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8

    EMAIL_PROVIDER: str = "mock"  # mock | outlook | gmail
    CENTRAL_EMAIL: str = "poupanca@empresa.com.br"

    OUTLOOK_CLIENT_ID: str = ""
    OUTLOOK_CLIENT_SECRET: str = ""
    OUTLOOK_TENANT_ID: str = ""
    OUTLOOK_REFRESH_TOKEN: str = ""

    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""

    SEED_ADMIN_EMAIL: str = "admin@empresa.com.br"
    SEED_ADMIN_PASSWORD: str

    CORS_ORIGINS: str = "http://localhost:3000"

    # Sync automática
    AUTO_SYNC_ENABLED: bool = True
    AUTO_SYNC_INTERVAL_SECONDS: int = 60

    # Keep-alive para Render (deixar vazio em desenvolvimento local)
    SELF_PING_URL: str = ""

    # Limite de dias para o primeiro sync (0 = sem limite)
    SYNC_INITIAL_DAYS: int = 0

    # Contas protegidas (não podem ser removidas pela UI/API). Lista por vírgula.
    PROTECTED_ACCOUNT_EMAILS: str = "contato@andradealves.adv.br"

    @property
    def protected_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.PROTECTED_ACCOUNT_EMAILS.split(",") if e.strip()}

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
