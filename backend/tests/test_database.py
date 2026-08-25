from pydantic import SecretStr
from sqlalchemy import make_url

from app.config import Settings
from app.database import create_engine


def test_component_password_with_url_characters_is_not_parsed_as_url_syntax() -> None:
    password = "p@ss:/?#%[] value"
    settings = Settings(database_password=SecretStr(password))

    url = settings.build_database_url()
    engine = create_engine(settings)

    assert url.password == password
    assert make_url(url.render_as_string(hide_password=False)).password == password
    assert engine.url.password == password


def test_explicit_percent_encoded_asyncpg_url_remains_supported() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:p%40ss%3Aword@db.example:5433/cooks"
    )

    url = settings.build_database_url()

    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p@ss:word"
    assert url.host == "db.example"
