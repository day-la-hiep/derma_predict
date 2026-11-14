from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_patient_fact_graph_service, get_patient_graph_context_service, require_internal_key
from app.dto.api import ApiResponse
from app.dto.patient_fact import (
    PatientFactOutput,
    PatientFactsApplyInput,
    PatientFactsApplyOutput,
    PatientFactsOutput,
    PatientGraphContextOutput,
    ProfileFactsReplaceInput,
)
from app.services.patient_fact_graph_service import PatientFactGraphService
from app.services.patient_graph_context_service import PatientGraphContextService

router = APIRouter(prefix="/internal/patient-facts", tags=["internal"], dependencies=[Depends(require_internal_key)])

PatientFacts = Annotated[PatientFactGraphService, Depends(get_patient_fact_graph_service)]
GraphContext = Annotated[PatientGraphContextService, Depends(get_patient_graph_context_service)]


@router.post("/apply", response_model=ApiResponse[PatientFactsApplyOutput])
async def apply_patient_facts(body: PatientFactsApplyInput, service: PatientFacts) -> ApiResponse[PatientFactsApplyOutput]:
    return ApiResponse(data=await service.apply_facts(body.patient_id, body.facts))


# khai báo trước các route `/{patient_id}` để "long-term" không bị hiểu là một patient_id
@router.get("/long-term", response_model=ApiResponse[dict[str, list[PatientFactOutput]]])
async def get_long_term_facts(profile_ids: str, service: PatientFacts) -> ApiResponse[dict[str, list[PatientFactOutput]]]:
    return ApiResponse(data=await service.get_long_term_facts([p.strip() for p in profile_ids.split(",") if p.strip()]))


@router.put("/{patient_id}/profile", response_model=ApiResponse[list[PatientFactOutput]])
async def replace_profile_facts(patient_id: str, body: ProfileFactsReplaceInput, service: PatientFacts) -> ApiResponse[list[PatientFactOutput]]:
    return ApiResponse(data=await service.replace_profile_facts(patient_id, body.facts))


@router.get("/{patient_id}/context", response_model=ApiResponse[PatientGraphContextOutput])
async def get_patient_graph_context(patient_id: str, service: GraphContext, top_k: int = 5) -> ApiResponse[PatientGraphContextOutput]:
    return ApiResponse(data=await service.get_context(patient_id, max(1, min(top_k, 10))))


@router.get("/{patient_id}", response_model=ApiResponse[PatientFactsOutput])
async def get_patient_facts(patient_id: str, service: PatientFacts, include_history: bool = False) -> ApiResponse[PatientFactsOutput]:
    return ApiResponse(data=await service.get_current_facts(patient_id, include_history))
