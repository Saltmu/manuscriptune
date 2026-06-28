import datetime
import os
import re
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.services import novel_service
from src.utils import project_config as writer_helper
from src.utils import project_paths
from src.utils.ai_client import AgyClient

router = APIRouter()


class FindingItem(BaseModel):
    id: str
    location: str
    original: str
    category: str
    severity: str
    analysis: str
    suggestion: str
    accepted: str
    apply_status: str | None = None
    apply_result: str | None = None


class SaveFindingsRequest(BaseModel):
    novel_name: str
    findings: list[FindingItem]


class SelectFileRequest(BaseModel):
    novel_name: str


class SaveNovelRequest(BaseModel):
    novel_name: str
    content: str


class WriteParams(BaseModel):
    episode: str
    novel_title: str | None = None
    policy_global: str | None = None
    policy_chapter: str | None = None
    character: str | None = None
    plot: str | None = None
    model: str | None = None
    step_by_step: bool = False
    self_check: bool = False


@router.get("/", response_class=HTMLResponse)
async def get_index():
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
        print(f"Error fetching models: {e}")
        return {"models": default_models}


@router.get("/api/novels")
async def list_novels():
    novel_dir = Path(project_paths.NOVELS_DIR)
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


@router.get("/api/novel")
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
    if yaml_path and os.path.exists(yaml_path):
        try:
            with open(yaml_path, encoding="utf-8") as f_yaml:
                data = yaml.safe_load(f_yaml)
                if data and "findings" in data:
                    findings = data["findings"]
        except Exception as e:
            print(f"Error reading YAML findings: {e}")

    # Read backup list
    backups = []
    basename = Path(novel_path).stem
    output_dir = project_paths.get_output_dir(basename)
    history_dir = os.path.join(output_dir, "history")
    if os.path.exists(history_dir):
        for d in os.listdir(history_dir):
            if os.path.isdir(os.path.join(history_dir, d)) and re.match(r"^v\d+$", d):
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
        "backups": backups,
    }


@router.post("/api/save_novel")
async def save_novel(req: SaveNovelRequest):
    try:
        novel_path, _ = novel_service.resolve_paths(req.novel_name)
    except HTTPException as he:
        raise he

    # Check protection
    if f"{project_paths.DATA_SOURCES_DIR}/" in novel_path.replace("\\", "/"):
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
        return {"status": "success", "message": "Novel saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save novel: {str(e)}")


@router.post("/api/save")
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
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                {"findings": findings_data},
                f,
                allow_unicode=True,
                default_flow_style=False,
            )
        return {"status": "success", "message": "Findings saved successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save findings: {str(e)}"
        )


@router.post("/api/backup")
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
        return {"status": "success", "message": "Backup created successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create backup: {str(e)}"
        )


@router.post("/api/rollback")
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


@router.get("/api/stream/apply")
async def stream_apply(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException as he:
        raise he
    try:
        # Automatically create backup before applying changes
        if os.path.exists(novel_path):
            shutil.copy2(novel_path, f"{novel_path}.bak")
        if os.path.exists(yaml_path):
            shutil.copy2(yaml_path, f"{yaml_path}.bak")

        basename = (
            Path(novel_path).stem.replace("_formatted", "").replace("_findings", "")
        )
        output_dir = project_paths.get_output_dir(basename)
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "apply_findings.py"
        )
        cmd = [
            "poetry",
            "run",
            "python",
            "-u",
            script_path,
            "--dir",
            output_dir,
            "--auto",
        ]

        return novel_service.stream_process_output(cmd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying changes: {str(e)}")


@router.post("/api/shutdown")
async def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(novel_service.shutdown_server)
    return {"status": "success", "message": "Shutting down..."}


@router.get("/api/stream/sync")
async def stream_sync():
    cmd = ["poetry", "run", "python", "-u", "src/sync_gdrive.py"]
    return novel_service.stream_process_output(cmd)


@router.get("/api/plots")
async def list_plots():
    sources_dir = Path(project_paths.DATA_SOURCES_DIR)
    if not sources_dir.exists():
        return {"plots": []}

    plots_list = []
    for f in sorted(sources_dir.glob("*.txt"), key=writer_helper.natural_sort_key):
        name = f.name
        if "プロット" in name or "plot" in name.lower() or name == "第1幕概要.txt":
            plot_stem = f.stem
            yaml_path = os.path.join(
                project_paths.DEFAULT_RESULTS_DIR,
                plot_stem,
                f"{plot_stem}_plot_findings.yaml",
            )
            has_findings = os.path.exists(yaml_path)

            mtime = os.path.getmtime(f)
            dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            plots_list.append(
                {
                    "name": name,
                    "size": f.stat().st_size,
                    "mtime": dt,
                    "has_findings": has_findings,
                }
            )
    return {"plots": plots_list}


@router.get("/api/plot")
async def get_plot(
    file: str = Query(
        ..., description=f"Plot filename in {project_paths.DATA_SOURCES_DIR}/"
    ),
):
    safe_file = os.path.basename(file)
    plot_path = os.path.join(project_paths.DATA_SOURCES_DIR, safe_file)
    if not os.path.exists(plot_path):
        raise HTTPException(status_code=404, detail="Plot file not found.")

    with open(plot_path, encoding="utf-8") as f:
        content = f.read()

    plot_stem = Path(plot_path).stem
    yaml_path = os.path.join(
        project_paths.DEFAULT_RESULTS_DIR, plot_stem, f"{plot_stem}_plot_findings.yaml"
    )
    findings = []
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, encoding="utf-8") as f_yaml:
                data = yaml.safe_load(f_yaml)
                if data and "findings" in data:
                    findings = data["findings"]
        except Exception as e:
            print(f"Error reading plot YAML findings: {e}")

    return {
        "plot_name": safe_file,
        "content": content,
        "findings": findings,
    }


@router.get("/api/stream/plot_review")
async def stream_plot_review(
    file: str = Query(
        ..., description=f"Plot filename in {project_paths.DATA_SOURCES_DIR}/"
    ),
    model: str | None = Query(None),
):
    safe_file = os.path.basename(file)
    plot_path = os.path.join(project_paths.DATA_SOURCES_DIR, safe_file)
    if not os.path.exists(plot_path):
        raise HTTPException(status_code=404, detail="Plot file not found.")

    cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "src/run_plot_review_pipeline.py",
        plot_path,
    ]
    if model:
        cmd.extend(["--model", model])

    return novel_service.stream_process_output(cmd)


@router.get("/api/stream/review")
async def stream_review(
    file: str = Query(
        ..., description=f"Novel text filename in {project_paths.NOVELS_DIR}/"
    ),
    model: str | None = Query(None),
):
    safe_file = os.path.basename(file)
    novel_path = os.path.join(project_paths.NOVELS_DIR, safe_file)
    if not os.path.exists(novel_path):
        raise HTTPException(status_code=404, detail="Novel file not found.")

    # We call run_review_pipeline.py with --no-server to prevent recursive server loops
    cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "src/run_review_pipeline.py",
        novel_path,
        "--no-server",
    ]
    if model:
        cmd.extend(["--model", model])

    return novel_service.stream_process_output(cmd)


@router.get("/api/stream/write")
async def stream_write(params: WriteParams = Depends()):  # noqa: B008
    cmd = novel_service.build_writer_cmd(params)
    return novel_service.stream_process_output(cmd)


@router.get("/api/write/prompt")
async def get_write_prompt(params: WriteParams = Depends()):  # noqa: B008
    cmd = novel_service.build_writer_cmd(params)
    cmd.append("--prompt-only")

    import asyncio
    import subprocess

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt generation failed: {stderr.decode('utf-8')}",
        )

    return {"prompt": stdout.decode("utf-8")}


@router.get("/api/sync/status")
async def sync_status():
    sources_dir = Path(project_paths.DATA_SOURCES_DIR)
    if not sources_dir.exists():
        return {"sources": []}

    sources_list = []
    for f in sorted(sources_dir.glob("*.txt"), key=writer_helper.natural_sort_key):
        mtime = os.path.getmtime(f)
        dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        sources_list.append(
            {"name": f.name, "size": f.stat().st_size, "last_updated": dt}
        )
    return {"sources": sources_list}


@router.get("/api/preview")
async def preview_novel(
    file: str = Query(
        ..., description=f"Novel text filename in {project_paths.NOVELS_DIR}/"
    ),
):
    safe_file = os.path.basename(file)
    novel_path = os.path.abspath(os.path.join(project_paths.NOVELS_DIR, safe_file))
    print(
        f"[DEBUG] preview_novel: file={repr(file)}, safe_file={repr(safe_file)}, novel_path={repr(novel_path)}, exists={os.path.exists(novel_path)}, cwd={os.getcwd()}"
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


@router.post("/api/select")
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


@router.get("/api/data")
async def get_data(file: str = Query(..., description="Novel filename")):
    try:
        novel_path, yaml_path = novel_service.resolve_paths(file)
    except HTTPException:
        return {
            "novel_lines": [],
            "findings": [],
            "novel_filename": "ファイル未選択",
            "has_backup": False,
        }

    if not os.path.exists(novel_path):
        raise HTTPException(
            status_code=404, detail=f"Novel file not found: {novel_path}"
        )

    # Read novel lines
    with open(novel_path, encoding="utf-8") as f:
        novel_lines = [line.rstrip("\r\n") for line in f.readlines()]

    findings = []
    # Findings YAML might not exist yet if review hasn't run
    if yaml_path and os.path.exists(yaml_path):
        with open(yaml_path, encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or {}
                findings = data.get("findings", [])
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to parse YAML: {str(e)}"
                )

    has_backup = os.path.exists(f"{novel_path}.bak")

    # Read backup list
    backups = []
    basename = Path(novel_path).stem
    output_dir = project_paths.get_output_dir(basename)
    history_dir = os.path.join(output_dir, "history")
    if os.path.exists(history_dir):
        for d in os.listdir(history_dir):
            if os.path.isdir(os.path.join(history_dir, d)) and re.match(r"^v\d+$", d):
                backups.append(d)
        backups.sort(key=lambda x: int(x[1:]))

    return {
        "novel_lines": novel_lines,
        "findings": findings,
        "novel_filename": os.path.basename(novel_path),
        "has_backup": has_backup,
        "backups": backups,
    }
