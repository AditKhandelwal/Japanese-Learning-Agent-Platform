from fastapi import FastAPI, Request
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

app.include_router(user.router, prefix="/api/users", tags=["users"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["assessment"])
app.include_router(session.router,    prefix="/api/sessions",   tags=["sessions"])
app.include_router(chat.router,       prefix="/api/chat",       tags=["chat"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug/token")
async def debug_token(request: Request):
    """Temporary: decode token without verification to diagnose 401s. Remove after debugging."""
    from jose import jwt
    from fastapi import Request
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"error": "No Bearer token"}
    token = auth[7:]
    try:
        header = jwt.get_unverified_header(token)
        claims = jwt.get_unverified_claims(token)
        return {"header": header, "claims": {k: v for k, v in claims.items() if k != "sub"}}
    except Exception as e:
        return {"error": str(e), "token_prefix": token[:30]}
