"""Notification buttons carry their own authority, so the token is the guard."""

import time

import pytest

from app.services import action_tokens


@pytest.fixture(autouse=True)
def _fresh_secret():
    action_tokens._secret = ""
    action_tokens.ensure_secret()
    yield
    action_tokens._secret = ""


def test_a_fresh_token_verifies():
    token = action_tokens.make("approve", 42)
    assert action_tokens.verify("approve", 42, token) is True


def test_a_token_is_bound_to_its_device():
    token = action_tokens.make("approve", 42)
    assert action_tokens.verify("approve", 43, token) is False


def test_a_token_is_bound_to_its_action():
    """An approve button must not be replayable as an ignore."""
    token = action_tokens.make("approve", 42)
    assert action_tokens.verify("ignore", 42, token) is False


def test_an_expired_token_is_refused():
    token = action_tokens.make("approve", 42, ttl=-1)
    assert action_tokens.verify("approve", 42, token) is False


def test_garbage_is_refused():
    for junk in ("", "abc", "9999999999.", ".deadbeef", "notanumber.deadbeef"):
        assert action_tokens.verify("approve", 42, junk) is False


def test_a_forged_signature_is_refused():
    expires = int(time.time()) + 600
    assert action_tokens.verify("approve", 42, f"{expires}.{'0' * 32}") is False


def test_an_unknown_action_is_refused():
    token = action_tokens.make("approve", 42)
    assert action_tokens.verify("delete_everything", 42, token) is False


def test_tokens_do_not_verify_under_a_different_secret():
    token = action_tokens.make("approve", 42)
    action_tokens._secret = "outro-segredo-completamente-diferente"
    assert action_tokens.verify("approve", 42, token) is False
