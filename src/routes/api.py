import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from src.routes.novels import router as novels_router
from src.routes.plots import router as plots_router
from src.routes.sync import router as sync_router
from src.services import novel_service, process_manager
from src.utils import project_config as writer_helper
from src.utils import project_paths
from src.utils.ai_client import AgyClient
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Include the split sub-routers
router.include_router(novels_router)
router.include_router(plots_router)
router.include_router(sync_router)


@router.get("/", response_class=HTMLResponse)
async def get_index():
    # 1. Try to serve Vite build first
    root_dir = project_paths.PROJECT_ROOT
    vite_index = os.path.join(root_dir, "frontend/dist/index.html")
    if os.path.exists(vite_index):
        with open(vite_index, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    # 2. Fallback to legacy SSI template rendering during migration
    try:
        return novel_service.render_html_template("index.html")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Template rendering error: {str(e)}"
        )


@router.get("/api/config")
async def get_config(request: Request):
    novel_title = writer_helper.get_novel_setting("title", "重天の調律師")
    initial_novel = getattr(request.app.state, "initial_novel", "")
    return {"novel_title": novel_title, "initial_novel": initial_novel}


@router.get("/api/models")
async def list_available_models():
    default_models = [
        "Gemini 3.5 Flash (High)",
        "Gemini 3.5 Flash (Medium)",
        "Gemini 3.5 Flash (Low)",
    ]
    try:
        raw_models = AgyClient.list_models()
        models = []
        for m in raw_models:
            if "Fetching available models" in m:
                continue
            if m not in models:
                models.append(m)

        if not models:
            models = default_models
        return {"models": models}
    except Exception as e:
        logger.error(f"Error fetching models: {e}", exc_info=True)
        return {"models": default_models}


@router.get("/api/cancel")
async def cancel_process(request_id: str = Query(...)):
    """
    実行中のLLM処理（ストリーミング）をキャンセルする。

    Args:
        request_id: キャンセル対象のリクエストID

    Returns:
        {"status": "cancelled"} - キャンセル成功時
        404 - プロセスが見つからない場合
    """
    if not process_manager.cancel_process(request_id):
        raise HTTPException(status_code=404, detail="Process not found")

    return {"status": "cancelled"}


@router.post("/api/shutdown")
async def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(novel_service.shutdown_server)
    return {"status": "success", "message": "Shutting down..."}
