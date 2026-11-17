from backend.app.integrations.aws.mock_adapter import AwsSecurityAdapter
from backend.app.models.schemas import TargetLookupResponse, TargetQueryRequest
from backend.app.services.plans import PlanService


def test_mock_adapter_finds_known_ipv4_in_expected_account():
    adapter = AwsSecurityAdapter()
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")

    result = adapter.query_target("123456789012", target)

    assert result.status == "found"
    assert "IP Set ccoe-blocklist-ipv4" in result.locations


def test_mock_adapter_returns_not_found_for_unknown_domain():
    adapter = AwsSecurityAdapter()
    target = TargetLookupResponse(kind="domain", normalized="unknown.example", display="DOMÍNIO · unknown.example")

    result = adapter.query_target("123456789012", target)

    assert result.status == "not_found"
    assert result.locations == []


def test_plan_service_queries_every_requested_account():
    service = PlanService(AwsSecurityAdapter())
    request = TargetQueryRequest(
        account_ids=["123456789012", "210987654321"],
        target="https://example.com/path",
    )

    result = service.query_target(request)

    assert result.mode == "mocked"
    assert result.target.normalized == "example.com"
    assert [match.account_id for match in result.matches] == ["123456789012", "210987654321"]
    assert result.matches[0].status == "found"
    assert result.matches[1].status == "not_found"


def test_plan_service_rejects_unknown_account():
    service = PlanService(AwsSecurityAdapter())
    request = TargetQueryRequest(account_ids=["999999999999"], target="192.0.2.10")

    try:
        service.query_target(request)
    except ValueError as error:
        assert "não autorizada" in str(error)
    else:
        raise AssertionError("A consulta deveria rejeitar uma conta desconhecida")
