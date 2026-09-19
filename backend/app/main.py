from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.goals import router as goals_router
from app.api.webhooks import router as webhooks_router
from app.mcp_server import McpEndpoint

mcp_endpoint = McpEndpoint()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp_endpoint.lifespan():
        yield


app = FastAPI(title="Bankr API", lifespan=lifespan)

# Dev-only: the web app runs on Vite's default port. Tighten to the real
# deployed origin once the web app has one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(dashboard_router)
app.include_router(goals_router)
app.include_router(chat_router)
app.include_router(webhooks_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

# Must stay last: mounted at "/" so exactly /mcp works (no trailing-slash
# redirect), which means it would shadow any route registered after it.
app.mount("/", mcp_endpoint)
