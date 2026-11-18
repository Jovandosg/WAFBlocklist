from unittest.mock import Mock, call, patch

import pytest
from botocore.exceptions import ClientError

from backend.app.integrations.aws.mock_adapter import AwsSecurityAdapter
from backend.app.models.schemas import TargetLookupResponse, TargetQueryMatch, TargetQueryRequest
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


def test_mock_adapter_labels_regional_results_with_selected_region():
    adapter = AwsSecurityAdapter()
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")

    result = adapter.query_target("123456789012", target, scope="REGIONAL", region="us-west-2")

    assert result.locations == ["IP Set ccoe-blocklist-ipv4 · us-west-2"]


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


def test_regional_query_uses_selected_region_and_scope():
    adapter = AwsSecurityAdapter()
    adapter.mock_mode = False
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")
    waf = Mock()
    waf.list_ip_sets.return_value = {"IPSets": [{"Name": "regional-blocklist", "Id": "set-id"}]}
    waf.get_ip_set.return_value = {"IPSet": {"Addresses": ["192.0.2.10/32"]}}
    session = Mock()
    session.client.return_value = waf

    with patch.object(adapter, "_session_for", return_value=session):
        result = adapter.query_target(
            "123456789012",
            target,
            scope="REGIONAL",
            region="us-west-2",
        )

    session.client.assert_called_once_with("wafv2", region_name="us-west-2")
    waf.list_ip_sets.assert_called_once_with(Scope="REGIONAL", Limit=100)
    waf.get_ip_set.assert_called_once_with(Name="regional-blocklist", Scope="REGIONAL", Id="set-id")
    assert result.status == "found"
    assert result.locations == ["IP Set regional-blocklist"]


def test_all_scope_queries_every_region_once_and_reports_partial_failures():
    adapter = AwsSecurityAdapter()
    adapter.list_accounts()
    adapter.mock_mode = False
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")
    session = Mock()

    def region_result(account_id, target, scope, region, *, session):
        if scope == "REGIONAL" and region == "us-west-2":
            return TargetQueryMatch(account_id=account_id, account_name="core-platform", status="error", detail="Access denied")
        locations = ["IP Set blocklist"] if scope == "REGIONAL" and region == "us-east-1" else []
        return TargetQueryMatch(
            account_id=account_id,
            account_name="core-platform",
            status="found" if locations else "not_found",
            locations=locations,
        )

    with patch("backend.app.integrations.aws.mock_adapter.AWS_WAF_REGIONS", {"us-east-1", "us-west-2"}), \
            patch.object(adapter, "_session_for", return_value=session) as assume, \
            patch.object(adapter, "query_target", side_effect=region_result) as query:
        result = adapter.query_target_all("123456789012", target)

    assume.assert_called_once_with("123456789012")
    query.assert_has_calls([
        call("123456789012", target, "CLOUDFRONT", "us-east-1", session=session),
        call("123456789012", target, "REGIONAL", "us-east-1", session=session),
        call("123456789012", target, "REGIONAL", "us-west-2", session=session),
    ], any_order=True)
    assert query.call_count == 3
    assert result.status == "partial"
    assert result.locations == ["REGIONAL · us-east-1 · IP Set blocklist"]
    assert result.errors == ["REGIONAL · us-west-2: Access denied"]


def test_all_scope_reports_account_access_failure_without_claiming_not_found():
    adapter = AwsSecurityAdapter()
    adapter.list_accounts()
    adapter.mock_mode = False
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "AssumeRole")

    with patch.object(adapter, "_session_for", side_effect=error):
        result = adapter.query_target_all("123456789012", target)

    assert result.status == "error"
    assert "Falha ao acessar a conta" in result.detail


def test_cloudfront_distribution_alone_does_not_count_as_target_match():
    adapter = AwsSecurityAdapter()
    adapter.mock_mode = False
    target = TargetLookupResponse(kind="ipv4", normalized="192.0.2.10/32", display="IPV4 · 192.0.2.10/32")
    waf = Mock()
    waf.list_ip_sets.return_value = {"IPSets": []}
    waf.list_web_acls.return_value = {"WebACLs": [{"Name": "ccoe-cloudfront-blocklist", "Id": "acl", "ARN": "arn:acl"}]}
    waf.get_web_acl.return_value = {"WebACL": {"Rules": []}}
    session = Mock()
    session.client.return_value = waf

    result = adapter.query_target("123456789012", target, session=session)

    assert result.status == "not_found"
    session.client.assert_called_once_with("wafv2", region_name="us-east-1")


def test_live_adapter_lists_active_subaccounts_and_excludes_master():
    adapter = AwsSecurityAdapter()
    adapter.mock_mode = False
    adapter.master_account_id = "588361999793"
    organizations = Mock()
    organizations.get_paginator.return_value.paginate.return_value = [{
        "Accounts": [
            {"Id": "588361999793", "Name": "master", "State": "ACTIVE"},
            {"Id": "111111111111", "Name": "active-child", "State": "ACTIVE"},
            {"Id": "222222222222", "Name": "suspended-child", "State": "SUSPENDED"},
        ],
    }]
    session = Mock()
    session.client.return_value = organizations

    with patch.object(adapter, "_master_session", return_value=session):
        accounts = adapter.list_accounts()

    organizations.get_paginator.assert_called_once_with("list_accounts")
    assert [(account.id, account.name) for account in accounts] == [
        ("111111111111", "active-child"),
    ]


def test_master_session_rejects_credentials_from_another_account():
    adapter = AwsSecurityAdapter()
    adapter.mock_mode = False
    adapter.master_account_id = "588361999793"
    session = Mock()
    session.client.return_value.get_caller_identity.return_value = {"Account": "111111111111"}

    with patch("backend.app.integrations.aws.mock_adapter.boto3.Session", return_value=session):
        with pytest.raises(RuntimeError, match="devem pertencer à conta master"):
            adapter._master_session()


def test_live_adapter_assumes_read_only_role_from_master_session():
    adapter = AwsSecurityAdapter()
    adapter.mock_mode = False
    adapter.master_account_id = "588361999793"
    adapter._accounts_by_id = {"111111111111": Mock(id="111111111111")}
    master_session = Mock()
    sts = master_session.client.return_value
    sts.get_caller_identity.return_value = {"Account": adapter.master_account_id}
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "temporary-access-key",
            "SecretAccessKey": "temporary-secret-key",
            "SessionToken": "temporary-session-token",
        },
    }
    assumed_session = Mock()

    with patch(
        "backend.app.integrations.aws.mock_adapter.boto3.Session",
        side_effect=[master_session, assumed_session],
    ):
        result = adapter._session_for("111111111111")

    assert result is assumed_session
    assume_role = sts.assume_role.call_args.kwargs
    assert assume_role["RoleArn"] == "arn:aws:iam::111111111111:role/wafblocklist-readonly-query"
    assert assume_role["ExternalId"] == "wafblocklist-target-111111111111-v1"
    assert assume_role["SourceIdentity"].startswith("waf-query-")
    assert assume_role["DurationSeconds"] == 900
