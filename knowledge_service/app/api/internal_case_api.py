import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_case_index_service, get_clinical_http, get_patient_journey_service, require_internal_key
from app.dto.common import ApiResponse
from app.dto.request.case import CaseInput
from app.dto.response.patient_graph import PatientJourneyGraphOutput
from app.services.case_index_service import CaseIndexService
from app.services.patient_journey_service import PatientJourneyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)])

CaseIndex = Annotated[CaseIndexService, Depends(get_case_index_service)]
Journey = Annotated[PatientJourneyService, Depends(get_patient_journey_service)]
ClinicalHttp = Annotated[httpx.AsyncClient, Depends(get_clinical_http)]

REINDEX_PAGE_SIZE = 50


class ReindexOutput(BaseModel):
    indexed: int
    failed: list[str]


class HistoryHintsOutput(BaseModel):
    conditions: list[str]
    advice: list[str]


@router.post("/cases", response_model=ApiResponse[None])
async def index_case(body: CaseInput, case_index: CaseIndex, journey: Journey) -> ApiResponse[None]:
    await case_index.index_case_async(body)
    await journey.sync_case(body)
    return ApiResponse(data=None)


@router.post("/cases/reindex", response_model=ApiResponse[ReindexOutput])
async def reindex_cases(case_index: CaseIndex, journey: Journey, clinical: ClinicalHttp) -> ApiResponse[ReindexOutput]:
    """Dựng lại Qdrant + đồ thị từ báo cáo đã chốt ở clinical; bù cho lời gọi `/cases` bị mất (không có outbox)."""
    indexed, failed, page = 0, [], 1
    while True:
        response = await clinical.get("/internal/finalize-reports", params={"page": page, "page_size": REINDEX_PAGE_SIZE})
        response.raise_for_status()
        cases = [CaseInput.model_validate(item) for item in response.json()["data"]]
        for case in cases:
            try:
                await case_index.index_case_async(case)
                await journey.sync_case(case)
                indexed += 1
            except Exception:  # noqa: BLE001
                logger.warning("Không reindex được báo cáo %s", case.report_id, exc_info=True)
                failed.append(case.report_id)
        if len(cases) < REINDEX_PAGE_SIZE:
            return ApiResponse(data=ReindexOutput(indexed=indexed, failed=failed))
        page += 1


@router.get("/patients/{patient_id}/history-hints", response_model=ApiResponse[HistoryHintsOutput])
async def get_history_hints(patient_id: str, journey: Journey) -> ApiResponse[HistoryHintsOutput]:
    conditions, advice = await journey.get_history_hints(patient_id)
    return ApiResponse(data=HistoryHintsOutput(conditions=conditions, advice=advice))


@router.get("/patients/{patient_id}/journey-graph", response_model=ApiResponse[PatientJourneyGraphOutput])
async def get_journey_graph(patient_id: str, journey: Journey) -> ApiResponse[PatientJourneyGraphOutput]:
    return ApiResponse(data=await journey.get_journey_graph(patient_id))
