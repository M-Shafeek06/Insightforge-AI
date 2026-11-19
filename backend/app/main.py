from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.upload import router as upload_router
from app.api.profiling import router as profiling_router
from app.api.quality import router as quality_router
from app.api.analysis import router as analysis_router
from app.api.execution import router as execution_router
from app.api.cleaning import router as cleaning_router
from app.api.dataset_versions import router as dataset_versions_router
from app.api.dataset_preview import router as dataset_preview_router
from app.api.ai_analysis import router as ai_analysis_router
from app.api.analytics_history import router as analytics_history_router
from app.api.saved_analytics import router as saved_analytics_router
from app.api.saved_artifacts import router as saved_artifacts_router
from app.api.reports import router as reports_router
from app.api.ai_interpretation import router as ai_interpretation_router

app = FastAPI(
    title="InsightForge AI API",
    version="0.1.0",
    description="Business Analytics & Decision Intelligence Platform API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(profiling_router, prefix="/api")
app.include_router(quality_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(execution_router, prefix="/api")
app.include_router(cleaning_router, prefix="/api")
app.include_router(dataset_versions_router, prefix="/api")
app.include_router(dataset_preview_router, prefix="/api")
app.include_router(ai_analysis_router, prefix="/api")
app.include_router(analytics_history_router, prefix="/api")
app.include_router(saved_analytics_router, prefix="/api")
app.include_router(saved_artifacts_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(ai_interpretation_router, prefix="/api")

@app.get("/")
def root() -> dict[str, str]:
    return {"name": "InsightForge AI API", "status": "running"}