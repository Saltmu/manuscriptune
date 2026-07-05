import asyncio
import datetime
import os
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.routes.deps import require_api_key
from src.routes.models.novels import (
    ChatRequest,
    ChatResponse,
    NovelDataResponse,
    NovelDetailResponse,
    NovelListResponse,
    NovelPreviewResponse,
    SaveFindingsRequest,
    SaveNovelRequest,
    SelectFileRequest,
    SelectFileResponse,
    StatusResponse,
    WriteParams,
    WritePromptResponse,
)
from src.services import (
    findings_service,
    novel_service,
    pipeline_service,
    stream_service,
    writer_service,
)
from src.services.chat_service import ChatService
from src.utils import path_safety, project_paths
from src.utils import project_config as writer_helper
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

router = APIRouter()
logger = get_logger(__name__)


@router.get("/api/novels", response_model=NovelListResponse)
async def list_novels():
    novel_dir = Path(project_paths.get_novels_dir())
    if not novel_dir.exists():
        return {"novels": []}

    novels_list = []
    for f in sorted(novel_dir.glob("*.txt"), key=writer_helper.natural_sort_key):
        # Resolve using dynamic resolution
        try:
            _, yaml_path = novel_service.resolve_paths(f.name)
            has_findings = os.path.exists(yaml_path)
        except Exception:
            has_findings = False

        mtime = os.path.getmtime(f)
        dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        novels_list.append(
            {
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": dt,
                "has_findings": has_findings,
            }
        )
    return {"novels": novels_list}


@router.get("/api/novel", response_model=NovelDetailResponse)
async def get_novel(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException as he:
        raise he

    if not os.path.exists(novel_path):
        raise HTTPException(status_code=404, detail="Novel file not found.")

    with open(novel_path, encoding="utf-8") as f:
        content = f.read()

    findings = []
    metadata = {}
    if yaml_path and os.path.exists(yaml_path):
        try:
            data = YamlHandler.load_safe(yaml_path)
            if isinstance(data, dict):
                findings = data.get("findings", [])
                metadata = data.get("_metadata", {})
            elif isinstance(data, list):
                findings = data
        except Exception as e:
            logger.error(f"Error reading YAML findings: {e}", exc_info=True)

    # Read backup list
    backups = []
    basename = Path(novel_path).stem
    output_dir = project_paths.get_output_dir(basename)
    history_dir = project_paths.get_history_dir(output_dir)
    if os.path.exists(history_dir):
        for d in os.listdir(history_dir):
            if os.path.isdir(project_paths.get_version_dir(output_dir, d)) and re.match(
                r"^v\d+$", d
            ):
                backups.append(d)
        backups.sort(key=lambda x: int(x[1:]))

    # Check for direct single backup
    novel_bak = f"{novel_path}.bak"
    if os.path.exists(novel_bak):
        backups.append(os.path.basename(novel_bak))

    return {
        "novel_name": file,
        "content": content,
        "findings": findings,
        "metadata": metadata,
        "backups": backups,
    }


@router.post(
    "/api/save_novel",
    response_model=StatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def save_novel(req: SaveNovelRequest):
    try:
        novel_path, _ = novel_service.resolve_paths(req.novel_name)
    except HTTPException as he:
        raise he

    # Check protection
    if path_safety.contains_source_segment(novel_path):
        logger.error(
            f"Violation: Attempt to save to source files in {project_paths.DATA_SOURCES_DIR}/"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Writing to source files in {project_paths.DATA_SOURCES_DIR}/ is strictly prohibited by AI guardrails.",
        )

    try:
        # Create a backup of the current state before saving if not already exists
        novel_bak = f"{novel_path}.bak"
        if os.path.exists(novel_path) and not os.path.exists(novel_bak):
            shutil.copy2(novel_path, novel_bak)

        with open(novel_path, "w", encoding="utf-8") as f:
            f.write(req.content)
        logger.info(f"Successfully saved novel file: {req.novel_name}")
        return {"status": "success", "message": "Novel saved successfully."}
    except Exception as e:
        logger.error(f"Failed to save novel '{req.novel_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save novel: {str(e)}")


@router.post(
    "/api/save", response_model=StatusResponse, dependencies=[Depends(require_api_key)]
)
async def save_findings(req: SaveFindingsRequest):
    try:
        _, yaml_path = novel_service.resolve_paths(req.novel_name)
    except HTTPException as he:
        raise he

    if not yaml_path:
        raise HTTPException(
            status_code=400, detail="No findings YAML path could be resolved."
        )

    try:
        os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
        # Create a backup of the current YAML state before saving
        yaml_bak = f"{yaml_path}.bak"
        if os.path.exists(yaml_path) and not os.path.exists(yaml_bak):
            shutil.copy2(yaml_path, yaml_bak)

        findings_data = [f.model_dump() for f in req.findings]
        dump_data: dict[str, Any] = {"findings": findings_data}
        if req.metadata:
            dump_data["_metadata"] = req.metadata
        YamlHandler.dump(dump_data, yaml_path)
        logger.info(f"Successfully saved findings YAML: {req.novel_name}")
        return {"status": "success", "message": "Findings saved successfully."}
    except Exception as e:
        logger.error(
            f"Failed to save findings YAML '{req.novel_name}': {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to save findings: {str(e)}"
        )


@router.post(
    "/api/backup",
    response_model=StatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def create_backup(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException as he:
        raise he

    try:
        if os.path.exists(novel_path):
            shutil.copy2(novel_path, f"{novel_path}.bak")
        if yaml_path and os.path.exists(yaml_path):
            shutil.copy2(yaml_path, f"{yaml_path}.bak")
        logger.info(f"Created backup for {file}")
        return {"status": "success", "message": "Backup created successfully."}
    except Exception as e:
        logger.error(f"Failed to create backup for {file}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create backup: {str(e)}"
        )


@router.post(
    "/api/rollback",
    response_model=StatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def rollback_backup(
    file: str = Query(..., description="Novel filename"),
    version: str | None = Query(
        None, description="Specific backup version folder to restore"
    ),
):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException as he:
        raise he

    return novel_service.rollback_backup(novel_path, yaml_path, version=version)


@router.get("/api/stream/apply", dependencies=[Depends(require_api_key)])
async def stream_apply(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException as he:
        raise he
    try:
        basename = (
            Path(novel_path).stem.replace("_formatted", "").replace("_findings", "")
        )
        # Automatically archive to history/v{next_version} before applying changes
        novel_service.archive_current_state(basename, extra_novel_path=novel_path)
        output_dir = project_paths.get_output_dir(basename)

        logger.info(f"Streaming apply_findings for novel: {file}")
        return stream_service.stream_service_call(
            findings_service.apply_findings_in_dir, output_dir, auto=True
        )
    except Exception as e:
        logger.error(f"Error applying changes for novel '{file}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error applying changes: {str(e)}")


@router.get("/api/stream/review", dependencies=[Depends(require_api_key)])
async def stream_review(
    file: str = Query(
        ..., description=f"Novel text filename in {project_paths.NOVELS_DIR}/"
    ),
    model: str | None = Query(None),
):
    safe_file = os.path.basename(file)
    novel_path = project_paths.get_novel_path(safe_file)
    if not os.path.exists(novel_path):
        raise HTTPException(status_code=404, detail="Novel file not found.")

    def _run_review(*, cancel_token=None, on_line=None):
        pipeline_service.TextReviewPipeline(
            target_file=novel_path,
            model=model or "Gemini 3.5 Flash (High)",
            cancel_token=cancel_token,
        ).execute(no_server=True)

    return stream_service.stream_service_call(_run_review)


def _resolve_safe_source_arg(field_name: str, value: str) -> str:
    """DATA_SOURCES_DIR配下に収まることを確認した上でパスを組み立てる。範囲外なら403。"""
    candidate = f"{project_paths.DATA_SOURCES_DIR}/{value}"
    if not path_safety.is_within(project_paths.DATA_SOURCES_DIR, candidate):
        raise HTTPException(status_code=403, detail=f"Invalid path for {field_name}.")
    return candidate


def _write_params_to_kwargs(params: WriteParams) -> dict[str, Any]:
    """WebのWriteParams(短いbasename指定)をWriterServiceの引数(解決済みフルパス)に変換する。"""
    kwargs: dict[str, Any] = {
        "episode": params.episode,
        "title": params.novel_title,
        "model": params.model,
        "step_by_step": params.step_by_step,
        "self_check": params.self_check,
        "include_neighbor_plots": params.include_neighbor_plots,
    }
    if params.policy_global:
        kwargs["policy_global"] = _resolve_safe_source_arg(
            "policy_global", params.policy_global
        )
    if params.policy_chapter:
        kwargs["policy_chapter"] = _resolve_safe_source_arg(
            "policy_chapter", params.policy_chapter
        )
    if params.character:
        kwargs["character"] = _resolve_safe_source_arg("character", params.character)
    if params.plot:
        kwargs["plot_file"] = _resolve_safe_source_arg("plot", params.plot)
    return kwargs


@router.get("/api/stream/write", dependencies=[Depends(require_api_key)])
async def stream_write(params: WriteParams = Depends()):  # noqa: B008
    # 執筆前に、もしすでにそのエピソードの小説ファイルが存在する場合は
    # レビュー時と同様に history/v{next_version}/ に退避させる
    try:
        plot_file = (
            _resolve_safe_source_arg("plot", params.plot) if params.plot else None
        )
        novel_path, basename = (
            writer_service.WriterService().resolve_episode_output_path(params.episode, plot_file=plot_file)
        )
        if os.path.exists(novel_path):
            logger.info(
                f"Existing novel file found for writing. Archiving: {novel_path}"
            )
            novel_service.archive_current_state(basename, extra_novel_path=novel_path)
    except Exception as e:
        logger.warning(f"Failed to archive prior to writing: {e}")

    kwargs = _write_params_to_kwargs(params)
    return stream_service.stream_service_call(
        writer_service.WriterService().execute, **kwargs
    )


@router.get(
    "/api/write/prompt",
    response_model=WritePromptResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_write_prompt(params: WriteParams = Depends()):  # noqa: B008
    kwargs = _write_params_to_kwargs(params)
    try:
        prompt = await asyncio.to_thread(
            writer_service.WriterService().generate_prompt, **kwargs
        )
    except writer_service.WriterServiceError as e:
        raise HTTPException(
            status_code=500, detail=f"Prompt generation failed: {e}"
        ) from e

    return {"prompt": prompt}


@router.get("/api/preview", response_model=NovelPreviewResponse)
async def preview_novel(
    file: str = Query(
        ..., description=f"Novel text filename in {project_paths.NOVELS_DIR}/"
    ),
):
    safe_file = os.path.basename(file)
    novel_path = project_paths.get_novel_path(safe_file)
    logger.debug(
        f"preview_novel: file={repr(file)}, safe_file={repr(safe_file)}, novel_path={repr(novel_path)}, exists={os.path.exists(novel_path)}, cwd={os.getcwd()}"
    )
    if not os.path.exists(novel_path):
        raise HTTPException(
            status_code=404,
            detail=f"Novel file not found: {novel_path} (CWD: {os.getcwd()})",
        )

    try:
        with open(novel_path, encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "filename": safe_file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read novel: {str(e)}")


@router.post("/api/select", response_model=SelectFileResponse)
async def select_file(payload: SelectFileRequest):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(payload.novel_name)
        return {
            "status": "success",
            "novel_path": novel_path,
            "yaml_path": yaml_path,
            "exists": os.path.exists(novel_path) and os.path.exists(yaml_path),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/data", response_model=NovelDataResponse)
async def get_data(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException:
        return {
            "novel_lines": [],
            "findings": [],
            "novel_filename": "ファイル未選択",
            "has_backup": False,
            "backups": [],
        }

    if not os.path.exists(novel_path):
        raise HTTPException(
            status_code=404, detail=f"Novel file not found: {novel_path}"
        )

    # Read novel lines
    with open(novel_path, encoding="utf-8") as f:
        novel_lines = [line.rstrip("\r\n") for line in f.readlines()]

    findings: list[Any] = []
    metadata: dict[str, Any] = {}
    # Findings YAML might not exist yet if review hasn't run
    if yaml_path and os.path.exists(yaml_path):
        try:
            data = YamlHandler.load(yaml_path)
            if isinstance(data, dict):
                findings = data.get("findings", [])
                metadata = data.get("_metadata", {})
            elif isinstance(data, list):
                findings = data
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to parse YAML: {str(e)}"
            )

    has_backup = os.path.exists(f"{novel_path}.bak")

    # Read backup list
    backups = []
    basename = Path(novel_path).stem
    output_dir = project_paths.get_output_dir(basename)
    history_dir = project_paths.get_history_dir(output_dir)
    if os.path.exists(history_dir):
        for d in os.listdir(history_dir):
            if os.path.isdir(project_paths.get_version_dir(output_dir, d)) and re.match(
                r"^v\d+$", d
            ):
                backups.append(d)
        backups.sort(key=lambda x: int(x[1:]))

    return {
        "novel_lines": novel_lines,
        "findings": findings,
        "metadata": metadata,
        "novel_filename": os.path.basename(novel_path),
        "has_backup": has_backup,
        "backups": backups,
    }


chat_service = ChatService()


@router.post("/api/findings/chat", response_model=ChatResponse)
async def chat_finding(req: ChatRequest):
    try:
        res = chat_service.chat(
            novel_name=req.novel_name,
            finding_id=req.finding_id,
            message=req.message,
            model=req.model,
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in chat_finding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
