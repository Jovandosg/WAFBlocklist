export type Environment = "production" | "staging" | "development";

export interface Account {
  id: string;
  name: string;
  environment: Environment;
  status: "authorized" | "restricted";
  distribution_count: number;
}

export interface Distribution {
  id: string;
  account_id: string;
  alias: string;
  web_acl_name: string | null;
}

export interface TargetLookup {
  kind: "ipv4" | "ipv6" | "domain";
  normalized: string;
  display: string;
}

export interface TargetQueryMatch {
  account_id: string;
  account_name: string;
  status: "found" | "not_found" | "partial" | "error";
  locations: string[];
  detail: string | null;
  errors: string[];
}

export interface TargetQueryResponse {
  target: TargetLookup;
  scope: WafScope;
  region: string;
  mode: "aws_read_only" | "mocked";
  matches: TargetQueryMatch[];
}

export type WafScope = "CLOUDFRONT" | "REGIONAL" | "ALL";

export interface ChangePlanRequest {
  account_ids: string[];
  add_ipv4: string[];
  remove_ipv4: string[];
  add_ipv6: string[];
  remove_ipv6: string[];
  add_asns: string[];
  remove_asns: string[];
  add_domains: string[];
  remove_domains: string[];
  attach_to_distributions: boolean;
  reason: string;
}

export interface ResourceSummary {
  ipv4_to_add: number;
  ipv4_to_remove: number;
  ipv6_to_add: number;
  ipv6_to_remove: number;
  asns_to_add: number;
  asns_to_remove: number;
  domains_to_add: number;
  domains_to_remove: number;
  distributions_to_attach: number;
  manual_review_required: number;
}

export interface ChangePlan {
  id: string;
  mode: "DRY_RUN";
  status: "READY_FOR_APPROVAL" | "QUEUED" | "COMPLETED" | "FAILED";
  created_at: string;
  reason: string;
  account_ids: string[];
  accounts: Account[];
  request: ChangePlanRequest;
  summary: ResourceSummary;
  warnings: string[];
  distributions: Distribution[];
  note: string;
}

const API_PREFIX = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(" · ")
      : typeof body.detail === "string" ? body.detail : "Não foi possível concluir a operação.";
    throw new Error(detail);
  }
  return body as T;
}

export async function getAccounts(): Promise<Account[]> {
  const response = await request<{ items: Account[] }>("/accounts");
  return response.items;
}

export async function getWafRegions(): Promise<string[]> {
  const response = await request<{ items: string[] }>("/regions");
  return response.items;
}

export async function lookupTarget(target: string): Promise<TargetLookup> {
  return request<TargetLookup>("/targets/lookup", {
    method: "POST",
    body: JSON.stringify({ target }),
  });
}

export async function queryTarget(
  accountIds: string[],
  target: string,
  scope: WafScope,
  region: string,
): Promise<TargetQueryResponse> {
  return request<TargetQueryResponse>("/targets/query", {
    method: "POST",
    body: JSON.stringify({ account_ids: accountIds, target, scope, region }),
  });
}

export async function createPlan(payload: ChangePlanRequest): Promise<ChangePlan> {
  return request<ChangePlan>("/plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getHealth(): Promise<{ status: string; mode: string }> {
  return request<{ status: string; mode: string }>("/health");
}
