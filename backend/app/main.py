from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.database import init_db
from app.routers import chat, session, user, assessment


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Japanese Learning Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router,       prefix="/api/users",      tags=["users"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["assessment"])
app.include_router(session.router,    prefix="/api/sessions",   tags=["sessions"])
app.include_router(chat.router,       prefix="/api/chat",       tags=["chat"])


@app.get("/health")
async def health():
    return {"status": "ok"}
