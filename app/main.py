"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="URL Inspector", version="1.0")


@app.get("/health")
async def health() -> JSONResponse:
    """Return service health status."""
    return JSONResponse({"status": "ok"})
