from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Literal
from uuid import uuid4

from botocore.session import get_session
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DOMAIN_PATTERN = re.compile(r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}")
MAX_ASNS = 100
MAX_DOMAINS = 30
CLOUDFRONT_REGION = "us-east-1"
AWS_WAF_REGIONS = frozenset(get_session().get_available_regions("wafv2"))
WafScope = Literal["CLOUDFRONT", "REGIONAL"]


def split_lines(values: list[str]) -> list[str]:
    return [item.strip() for value in values for item in value.splitlines() if item.strip()]


def normalize_networks(values: list[str]) -> list[str]:
    normalized: set[str] = set()
    for raw in split_lines(values):
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError as exc:
            raise ValueError(f"IP ou CIDR inválido: {raw}") from exc
        normalized.add(str(network))
    return sorted(normalized, key=lambda value: (ipaddress.ip_network(value).version, value))


def normalize_asns(values: list[str]) -> list[int]:
    normalized: set[int] = set()
    for raw in split_lines(values):
        candidate = raw.upper().removeprefix("AS")
        try:
            asn = int(candidate)
        except ValueError as exc:
            raise ValueError(f"ASN inválido: {raw}") from exc
        if not 1 <= asn <= 4_294_967_295:
            raise ValueError(f"ASN fora do intervalo válido: {raw}")
        normalized.add(asn)
    return sorted(normalized)


def normalize_domains(values: list[str]) -> list[str]:
    normalized: set[str] = set()
    for raw in split_lines(values):
        domain = raw.strip().lower()
        domain = domain.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        domain = domain.removeprefix("*.")
        if not DOMAIN_PATTERN.fullmatch(domain):
            raise ValueError(f"Domínio inválido: {raw}")
        normalized.add(domain)
    return sorted(normalized)


class Account(BaseModel):
    id: str
    name: str
    environment: Literal["production", "staging", "development"]
    status: Literal["authorized", "restricted"]
    distribution_count: int


class Distribution(BaseModel):
    id: str
    account_id: str
    alias: str
    web_acl_name: str | None = None


class TargetLookupRequest(BaseModel):
    target: str = Field(min_length=1, max_length=2048)


class TargetLookupResponse(BaseModel):
    kind: Literal["ipv4", "ipv6", "domain"]
    normalized: str
    display: str


def normalize_target(raw: str) -> TargetLookupResponse:
    target = raw.strip()
    try:
        network = ipaddress.ip_network(target, strict=False)
        kind = "ipv4" if network.version == 4 else "ipv6"
        normalized = str(network)
        return TargetLookupResponse(kind=kind, normalized=normalized, display=f"{kind.upper()} · {normalized}")
    except ValueError:
        if re.fullmatch(r"\d+(?:\.\d+){3}", target):
            raise ValueError(f"IP ou CIDR inválido: {target}")
        domains = normalize_domains([target])
        normalized = domains[0]
        return TargetLookupResponse(kind="domain", normalized=normalized, display=f"DOMÍNIO · {normalized}")


class TargetQueryRequest(BaseModel):
    account_ids: list[str] = Field(min_length=1)
    target: str = Field(min_length=1, max_length=2048)
    scope: WafScope = "CLOUDFRONT"
    region: str = CLOUDFRONT_REGION

    @field_validator("region")
    @classmethod
    def region_is_supported(cls, value: str) -> str:
        if value not in AWS_WAF_REGIONS:
            raise ValueError(f"Região AWS não suportada para WAFv2: {value}")
        return value

    @model_validator(mode="after")
    def cloudfront_region_is_fixed(self) -> TargetQueryRequest:
        if self.scope == "CLOUDFRONT" and self.region != CLOUDFRONT_REGION:
            raise ValueError(f"O escopo CloudFront usa a região {CLOUDFRONT_REGION}.")
        return self


class TargetQueryMatch(BaseModel):
    account_id: str
    account_name: str
    status: Literal["found", "not_found", "error"]
    locations: list[str] = Field(default_factory=list)
    detail: str | None = None


class TargetQueryResponse(BaseModel):
    target: TargetLookupResponse
    scope: WafScope
    region: str
    mode: Literal["aws_read_only", "mocked"]
    matches: list[TargetQueryMatch]


class ChangePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_ids: list[str] = Field(min_length=1)
    add_ipv4: list[str] = Field(default_factory=list)
    remove_ipv4: list[str] = Field(default_factory=list)
    add_ipv6: list[str] = Field(default_factory=list)
    remove_ipv6: list[str] = Field(default_factory=list)
    add_asns: list[str] = Field(default_factory=list)
    remove_asns: list[str] = Field(default_factory=list)
    add_domains: list[str] = Field(default_factory=list)
    remove_domains: list[str] = Field(default_factory=list)
    attach_to_distributions: bool = False
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("account_ids")
    @classmethod
    def validate_accounts(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value.strip() for value in values))
        invalid = [value for value in unique if not value.isdigit() or len(value) != 12]
        if invalid:
            raise ValueError(f"ID de conta inválido: {', '.join(invalid)}")
        return unique

    @field_validator("add_ipv4", "remove_ipv4", "add_ipv6", "remove_ipv6")
    @classmethod
    def validate_networks(cls, values: list[str]) -> list[str]:
        return normalize_networks(values)

    @field_validator("add_asns", "remove_asns")
    @classmethod
    def validate_asns(cls, values: list[str]) -> list[str]:
        return [str(asn) for asn in normalize_asns(values)]

    @field_validator("add_domains", "remove_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        return normalize_domains(values)

    @model_validator(mode="after")
    def validate_conflicts(self) -> "ChangePlanRequest":
        conflicts = [
            (set(self.add_ipv4) & set(self.remove_ipv4), "IPv4"),
            (set(self.add_ipv6) & set(self.remove_ipv6), "IPv6"),
            (set(self.add_asns) & set(self.remove_asns), "ASN"),
            (set(self.add_domains) & set(self.remove_domains), "domínio"),
        ]
        for values, label in conflicts:
            if values:
                raise ValueError(f"O mesmo {label} não pode ser adicionado e removido: {', '.join(sorted(values))}")
        if len(self.add_asns) > MAX_ASNS or len(self.remove_asns) > MAX_ASNS:
            raise ValueError(f"Máximo de {MAX_ASNS} ASNs por regra")
        if len(self.add_domains) > MAX_DOMAINS or len(self.remove_domains) > MAX_DOMAINS:
            raise ValueError(f"Máximo de {MAX_DOMAINS} domínios por regra")
        if not any([
            self.add_ipv4, self.remove_ipv4, self.add_ipv6, self.remove_ipv6,
            self.add_asns, self.remove_asns, self.add_domains, self.remove_domains,
            self.attach_to_distributions,
        ]):
            raise ValueError("Informe ao menos uma alteração para criar o plano")
        return self


class ResourceSummary(BaseModel):
    ipv4_to_add: int = 0
    ipv4_to_remove: int = 0
    ipv6_to_add: int = 0
    ipv6_to_remove: int = 0
    asns_to_add: int = 0
    asns_to_remove: int = 0
    domains_to_add: int = 0
    domains_to_remove: int = 0
    distributions_to_attach: int = 0
    manual_review_required: int = 0


class ChangePlan(BaseModel):
    id: str = Field(default_factory=lambda: f"pln_{uuid4().hex[:10]}")
    mode: Literal["DRY_RUN"] = "DRY_RUN"
    status: Literal["READY_FOR_APPROVAL", "QUEUED", "COMPLETED", "FAILED"] = "READY_FOR_APPROVAL"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reason: str
    account_ids: list[str]
    accounts: list[Account]
    request: ChangePlanRequest
    summary: ResourceSummary
    warnings: list[str] = Field(default_factory=list)
    distributions: list[Distribution] = Field(default_factory=list)
    note: str = "Nenhuma alteração foi aplicada. Este boilerplate opera somente em DRY-RUN."
