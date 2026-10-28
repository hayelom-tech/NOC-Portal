from dotenv import load_dotenv

load_dotenv()

import os

sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
        environment=os.getenv("APP_ENV", "development"),
    )

from server.application import create_app


app = create_app()
