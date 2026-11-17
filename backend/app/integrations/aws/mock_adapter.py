from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from backend.app.models.schemas import (
    Account,
    CLOUDFRONT_REGION,
    Distribution,
    TargetLookupResponse,
    TargetQueryMatch,
    WafScope,
)

ROLE_NAME = os.getenv("AWS_ROLE_NAME", "OrganizationAccountAccessRole")
REGION = os.getenv("AWS_REGION", "us-east-1")
ACL_NAME = "ccoe-cloudfront-blocklist"
IPSET_NAMES = {"ipv4": "ccoe-blocklist-ipv4", "ipv6": "ccoe-blocklist-ipv6"}


class AwsSecurityAdapter:
    """Leitura de segurança por conta; nenhuma operação mutável é feita neste adapter."""

    def __init__(self) -> None:
        configured_accounts = os.getenv("AWS_ACCOUNT_IDS", "")
        self.account_ids = [item.strip() for item in configured_accounts.split(",") if item.strip()]
        self.mock_mode = not self.account_ids or os.getenv("USE_MOCK_AWS", "false").lower() == "true"

    def list_accounts(self) -> list[Account]:
        if self.mock_mode:
            return [
                Account(id="123456789012", name="core-platform", environment="production", status="authorized", distribution_count=4),
                Account(id="210987654321", name="digital-products", environment="production", status="authorized", distribution_count=3),
                Account(id="345678901234", name="sandbox-lab", environment="development", status="authorized", distribution_count=2),
            ]

        return [
            Account(id=account_id, name=f"aws-account-{account_id[-4:]}", environment="production", status="authorized", distribution_count=0)
            for account_id in self.account_ids
        ]

    def list_distributions(self, account_ids: list[str]) -> list[Distribution]:
        if self.mock_mode:
            distributions = [
                Distribution(id="E1CORE01", account_id="123456789012", alias="app.example.com"),
                Distribution(id="E1CORE02", account_id="123456789012", alias="cdn.example.com", web_acl_name="managed-existing-acl"),
                Distribution(id="E1CORE03", account_id="123456789012", alias="assets.example.com"),
                Distribution(id="E1DIGI01", account_id="210987654321", alias="shop.example.com"),
                Distribution(id="E1DIGI02", account_id="210987654321", alias="checkout.example.com", web_acl_name="pci-protection-acl"),
                Distribution(id="E1LAB01", account_id="345678901234", alias="lab.example.net"),
            ]
            return [distribution for distribution in distributions if distribution.account_id in account_ids]

        result: list[Distribution] = []
        for account_id in account_ids:
            try:
                session = self._session_for(account_id)
                cloudfront = session.client("cloudfront", region_name=REGION)
                for page in cloudfront.get_paginator("list_distributions").paginate():
                    for item in page.get("DistributionList", {}).get("Items", []):
                        aliases = item.get("Aliases", {}).get("Items", [])
                        result.append(Distribution(
                            id=item["Id"],
                            account_id=account_id,
                            alias=aliases[0] if aliases else item["DomainName"],
                            web_acl_name=item.get("WebACLId") or None,
                        ))
            except (BotoCoreError, ClientError, NoCredentialsError):
                continue
        return result

    def query_target(
        self,
        account_id: str,
        target: TargetLookupResponse,
        scope: WafScope = "CLOUDFRONT",
        region: str = CLOUDFRONT_REGION,
    ) -> TargetQueryMatch:
        account = next((item for item in self.list_accounts() if item.id == account_id), None)
        account_name = account.name if account else account_id
        if self.mock_mode:
            return self._mock_query(account_id, account_name, target, scope, region)

        try:
            session = self._session_for(account_id)
            waf_region = CLOUDFRONT_REGION if scope == "CLOUDFRONT" else region
            waf = session.client("wafv2", region_name=waf_region)
            locations: list[str] = []

            if target.kind in {"ipv4", "ipv6"}:
                if scope == "CLOUDFRONT":
                    ipset_name = IPSET_NAMES[target.kind]
                    ipsets = []
                    ipset = self._find_named(waf, "ip_sets", ipset_name, scope)
                    if ipset:
                        ipsets.append(ipset)
                else:
                    ipsets = self._list_all(waf, "ip_sets", scope)
                for ipset in ipsets:
                    detail = waf.get_ip_set(
                        Name=ipset["Name"],
                        Scope=scope,
                        Id=ipset["Id"],
                    )["IPSet"]
                    if target.normalized in detail.get("Addresses", []):
                        locations.append(f"IP Set {ipset['Name']}")

            if scope == "CLOUDFRONT":
                acl = self._find_named(waf, "web_acls", ACL_NAME, scope)
                web_acls = [acl] if acl else []
            elif target.kind == "domain":
                web_acls = self._list_all(waf, "web_acls", scope)
            else:
                web_acls = []

            for acl in web_acls:
                web_acl = waf.get_web_acl(
                    Name=acl["Name"],
                    Scope=scope,
                    Id=acl["Id"],
                )["WebACL"]
                if target.kind == "domain":
                    for rule in web_acl.get("Rules", []):
                        if rule.get("Name") != "block-domains":
                            continue
                        if self._statement_contains_domain(rule.get("Statement", {}), target.normalized):
                            locations.append(f"Web ACL {acl['Name']} / block-domains")
                            break

                if scope == "CLOUDFRONT":
                    cloudfront = session.client("cloudfront", region_name=CLOUDFRONT_REGION)
                    for page in cloudfront.get_paginator("list_distributions").paginate():
                        for distribution in page.get("DistributionList", {}).get("Items", []):
                            if distribution.get("WebACLId") == acl["ARN"]:
                                locations.append(f"CloudFront {distribution['Id']} associada à Web ACL")

            return TargetQueryMatch(
                account_id=account_id,
                account_name=account_name,
                status="found" if locations else "not_found",
                locations=locations,
                detail="Encontrado em recursos de configuração read-only." if locations else "Nenhuma ocorrência encontrada nos recursos consultados.",
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            return TargetQueryMatch(
                account_id=account_id,
                account_name=account_name,
                status="error",
                detail=f"Falha na consulta read-only: {exc}",
            )

    def _session_for(self, account_id: str) -> boto3.Session:
        current = boto3.Session()
        current_id = current.client("sts", region_name=REGION).get_caller_identity()["Account"]
        if account_id == current_id:
            return current
        credentials = current.client("sts", region_name=REGION).assume_role(
            RoleArn=f"arn:aws:iam::{account_id}:role/{ROLE_NAME}",
            RoleSessionName="ccoe-cf-blocklist-readonly",
        )["Credentials"]
        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=REGION,
        )

    @staticmethod
    def _list_all(client: Any, kind: str, scope: WafScope) -> list[dict[str, Any]]:
        marker: dict[str, str] = {}
        method = getattr(client, f"list_{kind}")
        key = {"ip_sets": "IPSets", "web_acls": "WebACLs"}[kind]
        items: list[dict[str, Any]] = []
        while True:
            page = method(Scope=scope, Limit=100, **marker)
            items.extend(page.get(key, []))
            next_marker = page.get("NextMarker")
            if not next_marker:
                return items
            marker = {"NextMarker": next_marker}

    @staticmethod
    def _find_named(client: Any, kind: str, name: str, scope: WafScope) -> dict[str, Any] | None:
        return next(
            (item for item in AwsSecurityAdapter._list_all(client, kind, scope) if item["Name"] == name),
            None,
        )

    @staticmethod
    def _statement_contains_domain(statement: dict[str, Any], target: str) -> bool:
        if "ByteMatchStatement" in statement:
            raw = statement["ByteMatchStatement"].get("SearchString", b"")
            return raw.decode(errors="ignore").lower() == target.lower()
        if "OrStatement" in statement:
            return any(AwsSecurityAdapter._statement_contains_domain(item, target) for item in statement["OrStatement"].get("Statements", []))
        if "AndStatement" in statement:
            return any(AwsSecurityAdapter._statement_contains_domain(item, target) for item in statement["AndStatement"].get("Statements", []))
        return False

    @staticmethod
    def _mock_query(
        account_id: str,
        account_name: str,
        target: TargetLookupResponse,
        scope: WafScope,
        region: str,
    ) -> TargetQueryMatch:
        known = {
            ("123456789012", "ipv4", "192.0.2.10/32"): "IP Set ccoe-blocklist-ipv4",
            ("123456789012", "domain", "example.com"): "Web ACL block-domains",
        }
        location = known.get((account_id, target.kind, target.normalized))
        if location and scope == "REGIONAL":
            location = f"{location} · {region}"
        return TargetQueryMatch(
            account_id=account_id,
            account_name=account_name,
            status="found" if location else "not_found",
            locations=[location] if location else [],
            detail="Resultado mockado para desenvolvimento." if location else "Nenhuma ocorrência encontrada no estado mockado.",
        )

    def apply(self, plan_id: str) -> None:
        raise NotImplementedError("Este adapter é somente leitura; a aplicação ainda não está habilitada")
