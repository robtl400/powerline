"""Redis URL password injection used for the Celery broker and backend."""

from app.redis_client import redis_url_with_password


def test_no_password_leaves_url_unchanged() -> None:
    assert redis_url_with_password("redis://redis:6379/0", "") == "redis://redis:6379/0"


def test_password_injected_when_url_has_no_credentials() -> None:
    assert (
        redis_url_with_password("redis://redis:6379/0", "s3cret")
        == "redis://:s3cret@redis:6379/0"
    )


def test_existing_credentials_win() -> None:
    url = "redis://:inurl@redis:6379/0"
    assert redis_url_with_password(url, "ignored") == url


def test_existing_user_and_password_win() -> None:
    url = "redis://user:inurl@redis:6379/0"
    assert redis_url_with_password(url, "ignored") == url


def test_rediss_scheme_preserved() -> None:
    assert (
        redis_url_with_password("rediss://redis:6380/1", "s3cret")
        == "rediss://:s3cret@redis:6380/1"
    )


def test_special_characters_are_percent_encoded() -> None:
    assert (
        redis_url_with_password("redis://redis:6379/0", "p@ss/w:rd#1")
        == "redis://:p%40ss%2Fw%3Ard%231@redis:6379/0"
    )


def test_celery_broker_and_backend_use_the_same_url() -> None:
    from app.celery_app import celery_app
    from app.config import settings

    expected = redis_url_with_password(settings.REDIS_URL, settings.REDIS_PASSWORD)
    assert celery_app.conf.broker_url == expected
    assert celery_app.conf.result_backend == expected
