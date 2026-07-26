import ipaddress

from rpc_server.ip_filter import _parse_allowed_ips, validate_allowed_ips


class TestValidateAllowedIps:
    def test_single_ipv4(self):
        valid, errors = validate_allowed_ips("127.0.0.1")
        assert valid == ["127.0.0.1"]
        assert errors == []

    def test_cidr_subnet(self):
        valid, errors = validate_allowed_ips("192.168.1.0/24")
        assert valid == ["192.168.1.0/24"]
        assert errors == []

    def test_ipv6(self):
        valid, errors = validate_allowed_ips("::1")
        assert valid == ["::1"]
        assert errors == []

    def test_multiple_entries_with_spaces(self):
        valid, errors = validate_allowed_ips("127.0.0.1, 192.168.1.0/24 , 10.0.0.5")
        assert valid == ["127.0.0.1", "192.168.1.0/24", "10.0.0.5"]
        assert errors == []

    def test_empty_string(self):
        valid, errors = validate_allowed_ips("")
        assert valid == []
        assert errors

    def test_whitespace_only(self):
        valid, errors = validate_allowed_ips("   ")
        assert valid == []
        assert errors

    def test_leading_comma(self):
        valid, errors = validate_allowed_ips(",127.0.0.1")
        assert valid == []
        assert errors

    def test_trailing_comma(self):
        valid, errors = validate_allowed_ips("127.0.0.1,")
        assert valid == []
        assert errors

    def test_double_comma(self):
        valid, errors = validate_allowed_ips("127.0.0.1,,10.0.0.5")
        assert valid == []
        assert errors

    def test_mixed_valid_and_invalid(self):
        valid, errors = validate_allowed_ips("127.0.0.1,not-an-ip")
        assert valid == ["127.0.0.1"]
        assert len(errors) == 1
        assert "not-an-ip" in errors[0]

    def test_hostname_rejected(self):
        valid, errors = validate_allowed_ips("localhost")
        assert valid == []
        assert errors


class TestParseAllowedIps:
    def test_returns_networks(self):
        networks = _parse_allowed_ips("127.0.0.1, 192.168.1.0/24")
        assert networks == [
            ipaddress.ip_network("127.0.0.1"),
            ipaddress.ip_network("192.168.1.0/24"),
        ]

    def test_skips_invalid_entries(self):
        networks = _parse_allowed_ips("127.0.0.1,bogus")
        assert networks == [ipaddress.ip_network("127.0.0.1")]

    def test_host_bits_tolerated(self):
        # strict=False: a host address with a prefix is normalised, not rejected
        networks = _parse_allowed_ips("192.168.1.5/24")
        assert networks == [ipaddress.ip_network("192.168.1.0/24")]

    def test_membership(self):
        networks = _parse_allowed_ips("192.168.1.0/24")
        assert ipaddress.ip_address("192.168.1.77") in networks[0]
        assert ipaddress.ip_address("10.0.0.1") not in networks[0]
