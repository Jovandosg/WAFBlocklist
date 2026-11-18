from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_lookup_endpoint_normalizes_url():
    response = client.post("/api/v1/targets/lookup", json={"target": "https://Example.com/path"})

    assert response.status_code == 200
    assert response.json() == {
        "kind": "domain",
        "normalized": "example.com",
        "display": "DOMÍNIO · example.com",
    }


def test_health_endpoint_reports_mock_mode():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "mocked-dry-run"


def test_query_endpoint_returns_one_result_per_connected_account():
    response = client.post(
        "/api/v1/targets/query",
        json={
            "account_ids": ["123456789012", "210987654321", "345678901234"],
            "target": "192.0.2.10",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mocked"
    assert body["target"]["normalized"] == "192.0.2.10/32"
    assert body["scope"] == "CLOUDFRONT"
    assert body["region"] == "us-east-1"
    assert len(body["matches"]) == 3
    assert body["matches"][0]["status"] == "found"
    assert body["matches"][0]["locations"] == ["IP Set ccoe-blocklist-ipv4"]
    assert all(match["status"] == "not_found" for match in body["matches"][1:])


def test_regions_endpoint_lists_supported_waf_regions():
    response = client.get("/api/v1/regions")

    assert response.status_code == 200
    assert "us-east-1" in response.json()["items"]
    assert "us-west-2" in response.json()["items"]


def test_regional_query_accepts_selected_region():
    response = client.post(
        "/api/v1/targets/query",
        json={
            "account_ids": ["123456789012"],
            "target": "192.0.2.10",
            "scope": "REGIONAL",
            "region": "us-west-2",
        },
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "REGIONAL"
    assert response.json()["region"] == "us-west-2"


def test_all_scope_queries_global_and_regional_waf():
    response = client.post(
        "/api/v1/targets/query",
        json={"account_ids": ["123456789012"], "target": "192.0.2.10", "scope": "ALL"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "ALL"
    assert body["region"] == "all"
    assert body["matches"][0]["status"] == "found"
    assert any(location.startswith("CLOUDFRONT · us-east-1 ·") for location in body["matches"][0]["locations"])
    assert any(location.startswith("REGIONAL · us-west-2 ·") for location in body["matches"][0]["locations"])
    assert body["matches"][0]["errors"] == []


def test_cloudfront_query_rejects_region_other_than_us_east_1():
    response = client.post(
        "/api/v1/targets/query",
        json={
            "account_ids": ["123456789012"],
            "target": "192.0.2.10",
            "scope": "CLOUDFRONT",
            "region": "us-west-2",
        },
    )

    assert response.status_code == 422


def test_query_rejects_region_not_supported_by_wafv2():
    response = client.post(
        "/api/v1/targets/query",
        json={
            "account_ids": ["123456789012"],
            "target": "192.0.2.10",
            "scope": "REGIONAL",
            "region": "not-a-region",
        },
    )

    assert response.status_code == 422


def test_query_endpoint_reports_url_in_waf_rule():
    response = client.post(
        "/api/v1/targets/query",
        json={
            "account_ids": ["123456789012", "210987654321"],
            "target": "https://example.com/path",
        },
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert matches[0]["status"] == "found"
    assert matches[0]["locations"] == ["Web ACL block-domains"]
    assert matches[1]["status"] == "not_found"


def test_query_endpoint_rejects_unknown_account():
    response = client.post(
        "/api/v1/targets/query",
        json={"account_ids": ["999999999999"], "target": "192.0.2.10"},
    )

    assert response.status_code == 422
    assert "não autorizada" in response.json()["detail"]


def test_query_endpoint_rejects_invalid_target():
    response = client.post(
        "/api/v1/targets/query",
        json={"account_ids": ["123456789012"], "target": "not an ip or url"},
    )

    assert response.status_code == 422
    assert "Domínio inválido" in response.json()["detail"]
