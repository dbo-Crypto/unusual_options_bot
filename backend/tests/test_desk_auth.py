from fastapi import HTTPException

from app.desk_auth import assert_desk_token


def test_empty_token_allows_all():
    assert_desk_token("", "")
    assert_desk_token("", "anything")


def test_wrong_token_rejected():
    try:
        assert_desk_token("secret", "nope")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected 401")


def test_matching_token_ok():
    assert_desk_token("secret", "secret")
