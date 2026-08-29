import base64

from rpc_server.ip_filter import authorization_ok


TOKEN = "s3cret-token"


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class TestAuthorizationOk:
    def test_bearer_match(self):
        assert authorization_ok(f"Bearer {TOKEN}", TOKEN) is True

    def test_bearer_mismatch(self):
        assert authorization_ok("Bearer wrong", TOKEN) is False

    def test_bearer_trailing_whitespace_tolerated(self):
        assert authorization_ok(f"Bearer {TOKEN}  ", TOKEN) is True

    def test_basic_password_field_match(self):
        # stdlib xmlrpc clients send http://:token@host as Basic with empty user
        assert authorization_ok(_basic("", TOKEN), TOKEN) is True

    def test_basic_username_ignored(self):
        assert authorization_ok(_basic("anyuser", TOKEN), TOKEN) is True

    def test_basic_wrong_password(self):
        assert authorization_ok(_basic("", "wrong"), TOKEN) is False

    def test_basic_invalid_base64(self):
        assert authorization_ok("Basic !!!not-base64!!!", TOKEN) is False

    def test_empty_header(self):
        assert authorization_ok("", TOKEN) is False

    def test_unknown_scheme(self):
        assert authorization_ok(f"Digest {TOKEN}", TOKEN) is False

    def test_token_with_colon(self):
        token = "with:colon"
        # partition on the first colon keeps the rest as the password
        assert authorization_ok(_basic("", token), token) is True
