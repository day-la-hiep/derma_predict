from typing import Annotated

from derma_shared.errors import ForbiddenError
from fastapi import APIRouter, Depends, Header, status

from agent.dto.schemas import TurnRequest
from app.config.settings import settings
from app.turn_runner import cancel_turn, start_turn


def require_internal_key(x_internal_key: Annotated[str | None, Header()] = None) -> None:
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise ForbiddenError("Thiếu hoặc sai X-Internal-Key.")


router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)])


@router.post("/turns", status_code=status.HTTP_202_ACCEPTED)
async def create_turn(body: TurnRequest) -> dict[str, bool]:
    start_turn(body)
    return {"accepted": True}


@router.post("/turns/{message_id}/cancel")
async def cancel_turn_by_message(message_id: str) -> dict[str, bool]:
    return {"cancelled": cancel_turn(message_id)}
