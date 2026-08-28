from oddsmith.config import Settings


def test_secrets_are_not_exposed_in_settings_repr():
    settings = Settings(
        the_odds_api_key="odds-secret",
        api_football_key="football-secret",
        database_url="postgresql://user:database-secret@example.test/db",
    )

    rendered = repr(settings)
    assert "odds-secret" not in rendered
    assert "football-secret" not in rendered
    assert "database-secret" not in rendered
