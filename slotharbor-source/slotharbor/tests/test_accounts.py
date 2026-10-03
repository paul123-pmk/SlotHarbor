import pytest
from test_domain import env


def test_password_hash_salted_and_checked():
    from slotharbor.accounts import password_hash, password_matches
    value = "a-test-only-passphrase"
    first, second = password_hash(value), password_hash(value)
    assert first != second and value not in first
    assert password_matches(value, first)
    assert not password_matches("wrong-value", first)
    assert not password_matches(value, "invalid")
    assert not password_matches(value, "unknown$aa$bb")
    assert not password_matches("x"*257, first)


@pytest.mark.parametrize("username", ["x", "with space", "<script>", "@name", "a"*41])
def test_invalid_username(env, username):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        env["accounts"].create_user(username, "test-only-password", "member", env["admin"]["id"])


def test_only_admin_creates_users(env):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        env["accounts"].create_user("third", "test-only-password", "member", env["member"]["id"])
    with pytest.raises(DomainError):
        env["accounts"].create_user("third", "test-only-password", "member")


def test_duplicate_username_case_insensitive(env):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError) as ex:
        env["accounts"].create_user("OWNER", "test-only-password", "member", env["admin"]["id"])
    assert ex.value.status == 409


def test_login_session_and_revocation(env):
    accounts = env["accounts"]
    raw, csrf, user = accounts.login("MEMBER", "test-only-long-passphrase")
    assert user["id"] == env["member"]["id"]
    assert accounts.session(raw)["csrf"] == csrf
    assert "password_hash" not in accounts.session(raw)["user"]
    with env["db"].read() as con:
        tokens = [r[0] for r in con.execute("select token_hash from sessions")]
    assert raw not in tokens
    accounts.revoke(raw)
    assert accounts.session(raw) is None


def test_throttle_commits_failure_counters(env):
    from slotharbor.errors import DomainError
    accounts = env["accounts"]
    for _ in range(8):
        with pytest.raises(DomainError) as ex:
            accounts.login("member", "not-the-password")
        assert ex.value.status == 401
    with pytest.raises(DomainError) as ex:
        accounts.login("member", "test-only-long-passphrase")
    assert ex.value.status == 429
    accounts.clock = lambda: env["now"]+901
    assert accounts.login("member", "test-only-long-passphrase")


def test_deactivation_revokes_sessions_and_blocks_login(env):
    from slotharbor.errors import DomainError
    accounts = env["accounts"]
    raw, _, _ = accounts.login("member", "test-only-long-passphrase")
    accounts.set_active(env["admin"]["id"], env["member"]["id"], False)
    assert accounts.session(raw) is None
    with pytest.raises(DomainError): accounts.login("member", "test-only-long-passphrase")
    accounts.set_active(env["admin"]["id"], env["member"]["id"], True)
    assert accounts.login("member", "test-only-long-passphrase")


def test_last_admin_protected(env):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        env["accounts"].set_active(env["admin"]["id"], env["admin"]["id"], False)


def test_password_reset_revokes_session(env):
    accounts = env["accounts"]
    raw, _, _ = accounts.login("member", "test-only-long-passphrase")
    accounts.reset_password_local("member", "replacement-test-password")
    assert accounts.session(raw) is None
    assert accounts.login("member", "replacement-test-password")


def test_session_expiry_and_bad_tokens(env):
    accounts = env["accounts"]
    raw, _ = accounts.new_session()
    assert accounts.session(raw)["user"] is None
    accounts.clock = lambda: env["now"]+901
    assert accounts.session(raw) is None
    assert accounts.session(None) is None
    assert accounts.session("a"*200) is None
