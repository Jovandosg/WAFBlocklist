import pytest

from backend.app.models.schemas import normalize_target


def test_normalize_ipv4_host_to_cidr():
    result = normalize_target("192.0.2.10")

    assert result.kind == "ipv4"
    assert result.normalized == "192.0.2.10/32"
    assert result.display == "IPV4 · 192.0.2.10/32"


def test_normalize_ipv4_network_keeps_cidr():
    result = normalize_target("198.51.100.0/24")

    assert result.kind == "ipv4"
    assert result.normalized == "198.51.100.0/24"


def test_normalize_ipv6_host_to_cidr():
    result = normalize_target("2001:db8::1")

    assert result.kind == "ipv6"
    assert result.normalized == "2001:db8::1/128"


def test_normalize_url_to_lowercase_domain_without_path():
    result = normalize_target("HTTPS://Example.COM/path?source=test")

    assert result.kind == "domain"
    assert result.normalized == "example.com"
    assert result.display == "DOMÍNIO · example.com"


@pytest.mark.parametrize("value", ["not an ip or url", "https://", "999.999.999.999", "*.invalid"])
def test_reject_invalid_target(value: str):
    with pytest.raises(ValueError):
        normalize_target(value)
