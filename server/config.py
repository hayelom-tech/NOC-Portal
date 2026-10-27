import os
from dotenv import load_dotenv

load_dotenv()


def app_environment() -> str:
    value = os.getenv("APP_ENV", "development").strip().casefold()
    if value not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production.")
    return value


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        if app_environment() != "production":
            return "postgresql+psycopg://noc_portal:dev-only-change-me@localhost:5432/noc_portal"
        raise RuntimeError(
            "DATABASE_URL is required. Configure a PostgreSQL connection string before starting the portal."
        )
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def jwt_secret() -> str:
    value = os.getenv("JWT_SECRET_KEY", "")
    if len(value) < 32:
        if app_environment() != "production":
            return "local-development-secret-change-this-before-deployment-0001"
        raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 characters.")
    return value


def allowed_hosts() -> list[str]:
    configured = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    return [host.strip() for host in configured.split(",") if host.strip()]


def cookie_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "true").strip().lower() not in {"false", "0", "no"}


def validate_runtime_config() -> None:
    """Fail closed when known local-only credentials are used in production."""
    mode = app_environment()
    secret = jwt_secret()
    if mode != "production":
        return

    hosts = allowed_hosts()
    if not hosts or "*" in hosts or "testserver" in hosts:
        raise RuntimeError("Set ALLOWED_HOSTS to explicit production hostnames; wildcard or test hosts are not allowed.")

    if secret == "local-development-secret-change-this-before-deployment-0001":
        raise RuntimeError("Set a unique JWT_SECRET_KEY before running in production.")
    if not cookie_secure():
        raise RuntimeError("COOKIE_SECURE must be true in production (serve the app over HTTPS).")
    if os.getenv("POSTGRES_PASSWORD", "") == "dev-only-change-me" or "dev-only-change-me" in os.getenv("DATABASE_URL", ""):
        raise RuntimeError("Replace the development PostgreSQL password before running in production.")
    if os.getenv("INITIAL_ADMIN_PASSWORD", "") == "ChangeMeNow123!":
        raise RuntimeError("Set a unique INITIAL_ADMIN_PASSWORD before running in production.")


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ACCESS_TOKEN_MINUTES = 30
COOKIE_NAME = "noc_access_token"
