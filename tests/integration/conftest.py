import pytest
from sqlalchemy import text

from core.config import settings
from core.database import DatabaseManager


@pytest.fixture(scope="session")
def db():
    manager = DatabaseManager(settings.DATABASE_URL)
    yield manager
    manager.engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(db):
    with db.engine.connect() as connection:
        connection.execute(text("TRUNCATE raw_payloads RESTART IDENTITY CASCADE"))
        connection.commit()
    yield