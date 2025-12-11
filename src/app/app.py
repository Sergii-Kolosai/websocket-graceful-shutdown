from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router as api_router
from app.core.lifecycle import LifespanContext, setup_lifespan, shutdown_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan hook that delegates startup/shutdown to lifecycle helpers.

    Args:
        app: FastAPI application instance.
    """
    lifespan_context: LifespanContext = await setup_lifespan(app)
    try:
        yield
    finally:
        await shutdown_lifespan(lifespan_context)


app = FastAPI(
    title='WebSocket graceful shutdown service',
    lifespan=lifespan,
)
app.include_router(api_router)
