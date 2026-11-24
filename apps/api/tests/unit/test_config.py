from app.core.config import Settings, get_settings


def test_settings_load_from_env_file() -> None:
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.qdrant_path  # embedded Qdrant has a path
    assert settings.chunk_size > settings.chunk_overlap


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_unknown_env_keys_are_ignored() -> None:
    # extra="ignore" means an unrelated key in .env must not raise
    settings = Settings(_env_file=None, SOME_UNKNOWN_KEY="x")
    assert settings.app_name
