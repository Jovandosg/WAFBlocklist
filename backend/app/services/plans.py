from backend.app.integrations.aws.mock_adapter import AwsSecurityAdapter
from backend.app.models.schemas import (
    ChangePlan,
    ChangePlanRequest,
    ResourceSummary,
    TargetQueryRequest,
    TargetQueryResponse,
    normalize_target,
)


class PlanService:
    def __init__(self, adapter: AwsSecurityAdapter | None = None) -> None:
        self.adapter = adapter or AwsSecurityAdapter()
        self._plans: dict[str, ChangePlan] = {}

    def list_accounts(self):
        return self.adapter.list_accounts()

    def create_plan(self, request: ChangePlanRequest) -> ChangePlan:
        accounts = {account.id: account for account in self.adapter.list_accounts()}
        unknown_accounts = [account_id for account_id in request.account_ids if account_id not in accounts]
        if unknown_accounts:
            raise ValueError(f"Conta(s) não autorizada(s) ou inexistente(s): {', '.join(unknown_accounts)}")

        selected_accounts = [accounts[account_id] for account_id in request.account_ids]
        distributions = self.adapter.list_distributions(request.account_ids)
        attachable = [distribution for distribution in distributions if distribution.web_acl_name is None]
        protected = [distribution for distribution in distributions if distribution.web_acl_name is not None]

        warnings = [
            "Modo DRY-RUN: nenhuma alteração será aplicada à AWS.",
            "Distribuições que já possuem outro WAF não serão substituídas automaticamente.",
        ]
        if request.attach_to_distributions and protected:
            warnings.append(f"{len(protected)} distribuição(ões) já possui(em) WAF e exige(m) revisão manual.")
        if not request.attach_to_distributions:
            distributions = []

        summary = ResourceSummary(
            ipv4_to_add=len(request.add_ipv4),
            ipv4_to_remove=len(request.remove_ipv4),
            ipv6_to_add=len(request.add_ipv6),
            ipv6_to_remove=len(request.remove_ipv6),
            asns_to_add=len(request.add_asns),
            asns_to_remove=len(request.remove_asns),
            domains_to_add=len(request.add_domains),
            domains_to_remove=len(request.remove_domains),
            distributions_to_attach=len(attachable) if request.attach_to_distributions else 0,
            manual_review_required=len(protected) if request.attach_to_distributions else 0,
        )
        plan = ChangePlan(
            reason=request.reason,
            account_ids=request.account_ids,
            accounts=selected_accounts,
            request=request,
            summary=summary,
            warnings=warnings,
            distributions=distributions,
        )
        self._plans[plan.id] = plan
        return plan

    def get_plan(self, plan_id: str) -> ChangePlan | None:
        return self._plans.get(plan_id)

    def query_target(self, request: TargetQueryRequest) -> TargetQueryResponse:
        known_accounts = {account.id for account in self.adapter.list_accounts()}
        unknown_accounts = [account_id for account_id in request.account_ids if account_id not in known_accounts]
        if unknown_accounts:
            raise ValueError(f"Conta(s) não autorizada(s) ou inexistente(s): {', '.join(unknown_accounts)}")
        target = normalize_target(request.target)
        if request.scope == "ALL":
            matches = [
                self.adapter.query_target_all(account_id, target)
                for account_id in request.account_ids
            ]
        else:
            matches = [
                self.adapter.query_target(account_id, target, request.scope, request.region)
                for account_id in request.account_ids
            ]
        return TargetQueryResponse(
            target=target,
            scope=request.scope,
            region="all" if request.scope == "ALL" else request.region,
            mode="mocked" if self.adapter.mock_mode else "aws_read_only",
            matches=matches,
        )


plan_service = PlanService()
