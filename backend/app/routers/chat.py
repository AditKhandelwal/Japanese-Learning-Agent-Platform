from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.database import get_db
from app.agent.orchestrator import AgentOrchestrator
from app.models.schemas import ChatRequest

router = APIRouter()


@router.post("/")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    orchestrator = AgentOrchestrator(db=db, user_id=body.user_id)

    async def event_stream():
        async for chunk in orchestrator.stream(
            message=body.message,
            session_id=body.session_id,
            mode=body.mode,
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
