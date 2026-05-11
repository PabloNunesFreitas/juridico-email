from app.core.config import settings
from app.models.email_account import EmailAccount
from app.providers.email_provider import EmailProvider
from app.providers.gmail_provider import GmailEmailProvider
from app.providers.mock_provider import MockEmailProvider
from app.providers.outlook_provider import OutlookEmailProvider


def get_email_provider() -> EmailProvider:
    """Factory legada: retorna provider global sem conta específica."""
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "outlook":
        return OutlookEmailProvider()
    if provider == "gmail":
        return GmailEmailProvider()
    return MockEmailProvider()


def get_provider_for_account(account: EmailAccount) -> EmailProvider:
    """Retorna provider instanciado para uma conta específica."""
    if account.provider == "gmail":
        return GmailEmailProvider(account)
    if account.provider == "outlook":
        return OutlookEmailProvider(account)
    return MockEmailProvider()
