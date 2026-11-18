from fastapi import APIRouter, HTTPException

from backend.app.models.schemas import AWS_WAF_REGIONS, ChangePlan, ChangePlanRequest, TargetLookupRequest, TargetLookupResponse, TargetQueryRequest, TargetQueryResponse, normalize_target
from backend.app.services.plans import plan_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    mode = "mocked-dry-run" if plan_service.adapter.mock_mode else "aws-read-only-dry-run"
    return {"status": "ok", "service": "wafblocklist-api", "mode": mode}


@router.get("/accounts")
def list_accounts():
    return {"items": plan_service.list_accounts()}


@router.get("/regions")
def list_waf_regions() -> dict[str, list[str]]:
    return {"items": sorted(AWS_WAF_REGIONS)}


@router.post("/targets/lookup", response_model=TargetLookupResponse)
def lookup_target(request: TargetLookupRequest):
    try:
        return normalize_target(request.target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/targets/query", response_model=TargetQueryResponse)
def query_target(request: TargetQueryRequest):
    try:
        return plan_service.query_target(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/validate")
def validate_request(request: ChangePlanRequest):
    return {
        "valid": True,
        "normalized": request,
        "message": "Entradas válidas e prontas para simulação.",
    }


@router.post("/plans", response_model=ChangePlan, status_code=201)
def create_plan(request: ChangePlanRequest):
    try:
        return plan_service.create_plan(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/plans/{plan_id}", response_model=ChangePlan)
def get_plan(plan_id: str):
    plan = plan_service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    return plan
