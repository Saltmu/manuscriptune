import argparse
import asyncio
import datetime
import os
import re
import shutil
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

import uvicorn
import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import apply_findings logic from apply_findings.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "skills", "novel-writer")
    )
)
import writer_helper

app = FastAPI(title="Novel Studio - AI Writing & Review Portal")

# Mount static directory for CSS/JS
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)

# Global variables to store paths
NOVEL_PATH = ""
YAML_PATH = ""


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
    findings: list[FindingItem]


class SelectFileRequest(BaseModel):
    novel_name: str


class SaveNovelRequest(BaseModel):
    content: str


def render_html_template(template_name: str) -> str:
    """Recursively resolves <!--#include file="filename.html"--> placeholders."""
    template_dir = Path(__file__).parent / "templates"
    template_path = template_dir / template_name

    if not template_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Template {template_name} not found"
        )

    with open(template_path, encoding="utf-8") as f:
        content = f.read()

    def replace_match(match):
        include_file = match.group(1)
        return render_html_template(include_file)

    # Pattern to match: <!--#include file="some/path.html"-->
    return re.sub(r'<!--#include file="([^"]+)"-->', replace_match, content)


# Helper to run a command and stream its output via SSE (Server-Sent Events)
def stream_process_output(cmd):
    async def event_generator():
        print(f"[INFO] Running process stream: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8")
            # Format as Server-Sent Event (SSE)
            yield f"data: {line.rstrip()}\n\n"

        rc = await process.wait()
        yield f"data: [PROCESS_EXITED] code={rc}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    try:
        return render_html_template("index.html")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Template rendering error: {str(e)}"
        )


@app.get("/api/config")
async def get_config():
    novel_title = writer_helper.get_novel_setting("title", "重天の調律師")
    return {"novel_title": novel_title}


@app.get("/api/models")
async def list_available_models():
    try:
        res = subprocess.run(["agy", "models"], capture_output=True, text=True)
        if res.returncode != 0:
            return {
                "models": [
                    "Gemini 3.5 Flash (High)",
                    "Gemini 3.5 Flash (Medium)",
                    "Gemini 3.5 Flash (Low)",
                ]
            }

        lines = res.stdout.strip().split("\n")
        models = []
        for line in lines:
            line_clean = (
                line.replace("⠋", "")
                .replace("⠙", "")
                .replace("⠹", "")
                .replace("⠸", "")
                .replace("⠼", "")
                .replace("⠴", "")
                .replace("⠦", "")
                .replace("⠧", "")
                .replace("⠇", "")
                .replace("⠏", "")
                .strip()
            )
            if not line_clean:
                continue
            if "Fetching available models" in line_clean:
                continue
            if line_clean not in models:
                models.append(line_clean)

        if not models:
            models = [
                "Gemini 3.5 Flash (High)",
                "Gemini 3.5 Flash (Medium)",
                "Gemini 3.5 Flash (Low)",
            ]
        return {"models": models}
    except Exception as e:
        print(f"Error fetching models: {e}")
        return {
            "models": [
                "Gemini 3.5 Flash (High)",
                "Gemini 3.5 Flash (Medium)",
                "Gemini 3.5 Flash (Low)",
            ]
        }


@app.get("/api/novels")
async def list_novels():
    novel_dir = Path("novels")
    if not novel_dir.exists():
        return {"novels": []}

    novels_list = []
    for f in sorted(novel_dir.glob("*.txt")):
        basename = f.stem
        findings_yaml = (
            Path("novel_check_results") / basename / "00_integrated_findings.yaml"
        )
        has_findings = findings_yaml.exists()

        mtime = os.path.getmtime(f)
        dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        novels_list.append(
            {
                "name": f.name,
                "size": f.stat().st_size,
                "last_modified": dt,
                "has_findings": has_findings,
                "findings_path": str(findings_yaml) if has_findings else None,
            }
        )
    return {"novels": novels_list}


@app.get("/api/sync/status")
async def sync_status():
    sources_dir = Path("data/sources")
    if not sources_dir.exists():
        return {"sources": []}

    sources_list = []
    for f in sorted(sources_dir.glob("*.txt")):
        mtime = os.path.getmtime(f)
        dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        sources_list.append(
            {"name": f.name, "size": f.stat().st_size, "last_updated": dt}
        )
    return {"sources": sources_list}


@app.get("/api/preview")
async def preview_novel(
    file: str = Query(..., description="Novel text filename in novels/"),
):
    safe_file = os.path.basename(file)
    novel_path = os.path.abspath(os.path.join("novels", safe_file))
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


@app.post("/api/select")
async def select_file(payload: SelectFileRequest):
    global NOVEL_PATH, YAML_PATH
    basename = Path(payload.novel_name).stem

    # Check if we have formatted check results
    formatted_path = os.path.abspath(
        os.path.join("novel_check_results", basename, "01_formatted.txt")
    )
    if os.path.exists(formatted_path):
        NOVEL_PATH = formatted_path
    else:
        NOVEL_PATH = os.path.abspath(os.path.join("novels", payload.novel_name))

    YAML_PATH = os.path.abspath(
        os.path.join("novel_check_results", basename, "00_integrated_findings.yaml")
    )

    return {
        "status": "success",
        "novel_path": NOVEL_PATH,
        "yaml_path": YAML_PATH,
        "exists": os.path.exists(NOVEL_PATH) and os.path.exists(YAML_PATH),
    }


@app.get("/api/data")
async def get_data():
    global NOVEL_PATH, YAML_PATH
    if not NOVEL_PATH or not YAML_PATH:
        return JSONResponse(
            content={
                "novel_lines": [],
                "findings": [],
                "novel_filename": "ファイル未選択",
                "has_backup": False,
            }
        )

    if not os.path.exists(NOVEL_PATH):
        raise HTTPException(
            status_code=404, detail=f"Novel file not found: {NOVEL_PATH}"
        )

    # Read novel lines
    with open(NOVEL_PATH, encoding="utf-8") as f:
        novel_lines = [line.rstrip("\r\n") for line in f.readlines()]

    findings = []
    # Findings YAML might not exist yet if review hasn't run
    if os.path.exists(YAML_PATH):
        with open(YAML_PATH, encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or {}
                findings = data.get("findings", [])
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to parse YAML: {str(e)}"
                )

    has_backup = os.path.exists(f"{NOVEL_PATH}.bak")

    return JSONResponse(
        content={
            "novel_lines": novel_lines,
            "findings": findings,
            "novel_filename": os.path.basename(NOVEL_PATH),
            "has_backup": has_backup,
        }
    )


@app.post("/api/save")
async def save_findings(payload: SaveFindingsRequest):
    global YAML_PATH
    if not YAML_PATH:
        raise HTTPException(status_code=400, detail="No active YAML file selected.")
    try:
        findings_list = [item.model_dump() for item in payload.findings]

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(YAML_PATH), exist_ok=True)

        # Write back to YAML
        with open(YAML_PATH, "w", encoding="utf-8") as f:
            yaml.dump(
                {"findings": findings_list},
                f,
                allow_unicode=True,
                default_flow_style=False,
            )

        return {"status": "success", "message": "Saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save YAML: {str(e)}")


@app.post("/api/save_novel")
async def save_novel(payload: SaveNovelRequest):
    global NOVEL_PATH
    if not NOVEL_PATH:
        raise HTTPException(status_code=400, detail="No active novel file selected.")
    try:
        # Write back to novel file
        with open(NOVEL_PATH, "w", encoding="utf-8") as f:
            f.write(payload.content)
        return {"status": "success", "message": "Novel saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save novel: {str(e)}")


@app.post("/api/backup")
async def create_backup():
    global NOVEL_PATH, YAML_PATH
    if not NOVEL_PATH:
        raise HTTPException(status_code=400, detail="No active novel file selected.")
    try:
        if os.path.exists(NOVEL_PATH):
            shutil.copy2(NOVEL_PATH, f"{NOVEL_PATH}.bak")
        if YAML_PATH and os.path.exists(YAML_PATH):
            shutil.copy2(YAML_PATH, f"{YAML_PATH}.bak")
        return {"status": "success", "message": "Backup created successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create backup: {str(e)}"
        )


@app.post("/api/rollback")
async def rollback_backup():
    global NOVEL_PATH, YAML_PATH
    if not NOVEL_PATH:
        raise HTTPException(status_code=400, detail="No active novel file selected.")

    novel_bak = f"{NOVEL_PATH}.bak"
    yaml_bak = f"{YAML_PATH}.bak" if YAML_PATH else None

    if not os.path.exists(novel_bak):
        raise HTTPException(
            status_code=404, detail="Backup file not found. Nothing to rollback."
        )

    try:
        # Restore novel file
        shutil.copy2(novel_bak, NOVEL_PATH)
        # Restore YAML file if backup exists
        if yaml_bak and os.path.exists(yaml_bak):
            shutil.copy2(yaml_bak, YAML_PATH)
        else:
            if YAML_PATH and os.path.exists(YAML_PATH):
                with open(YAML_PATH, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                findings = data.get("findings", [])
                for f in findings:
                    f["apply_status"] = None
                    f["apply_result"] = None
                with open(YAML_PATH, "w", encoding="utf-8") as f:
                    yaml.dump(
                        {"findings": findings},
                        f,
                        allow_unicode=True,
                        default_flow_style=False,
                    )

        return {"status": "success", "message": "Rollback completed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback: {str(e)}")


def shutdown_server():
    print("[INFO] Shutting down Review Editor server...")
    os.kill(os.getpid(), signal.SIGINT)


@app.get("/api/stream/apply")
async def stream_apply():
    global NOVEL_PATH, YAML_PATH
    if not NOVEL_PATH or not YAML_PATH:
        raise HTTPException(status_code=400, detail="No active file selected.")
    try:
        # Automatically create backup before applying changes
        if os.path.exists(NOVEL_PATH):
            shutil.copy2(NOVEL_PATH, f"{NOVEL_PATH}.bak")
        if os.path.exists(YAML_PATH):
            shutil.copy2(YAML_PATH, f"{YAML_PATH}.bak")

        parent_dir = os.path.dirname(NOVEL_PATH)
        script_path = os.path.join(os.path.dirname(__file__), "apply_findings.py")
        cmd = [
            "poetry",
            "run",
            "python",
            "-u",
            script_path,
            "--dir",
            parent_dir,
            "--auto",
        ]

        return stream_process_output(cmd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying changes: {str(e)}")


@app.post("/api/shutdown")
async def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(shutdown_server)
    return {"status": "success", "message": "Shutting down..."}


# === SSE Streaming Endpoints ===


@app.get("/api/stream/sync")
async def stream_sync():
    cmd = ["poetry", "run", "python", "-u", "src/sync_gdrive.py"]

    return stream_process_output(cmd)


@app.get("/api/stream/review")
async def stream_review(
    file: str = Query(..., description="Novel text filename in novels/"),
):
    safe_file = os.path.basename(file)
    novel_path = os.path.join("novels", safe_file)
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

    return stream_process_output(cmd)


@app.get("/api/stream/write")
async def stream_write(
    episode: str = Query(..., description="Episode title e.g. 第1話"),
    novel_title: str | None = Query(None),
    policy_global: str | None = Query(None),
    policy_chapter: str | None = Query(None),
    character: str | None = Query(None),
    plot: str | None = Query(None),
    model: str | None = Query(None),
    step_by_step: bool = Query(False),
    self_check: bool = Query(False),
):
    cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "skills/novel_writer_antigravitycli/writer_cli.py",
        "--episode",
        episode,
    ]

    if model:
        cmd.extend(["--model", model])
    if novel_title:
        cmd.extend(["--title", novel_title])
    if policy_global:
        cmd.extend(["--policy-global", f"data/sources/{policy_global}"])
    if policy_chapter:
        cmd.extend(["--policy-chapter", f"data/sources/{policy_chapter}"])
    if character:
        cmd.extend(["--character", f"data/sources/{character}"])
    if plot:
        cmd.extend(["--plot-file", f"data/sources/{plot}"])
    if step_by_step:
        cmd.append("--step-by-step")
    if self_check:
        cmd.append("--self-check")

    return stream_process_output(cmd)


async def open_browser(port):
    await asyncio.sleep(1)  # wait for server to start
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser(
        description="Start the Interactive Novel Studio Server."
    )
    parser.add_argument(
        "--novel", default=None, help="Initial path to the novel txt file."
    )
    parser.add_argument(
        "--yaml",
        default=None,
        help="Initial path to the integrated findings YAML file.",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to run the server on."
    )
    args = parser.parse_args()

    global NOVEL_PATH, YAML_PATH
    if args.novel:
        NOVEL_PATH = os.path.abspath(args.novel)
    if args.yaml:
        YAML_PATH = os.path.abspath(args.yaml)

    print("=== Novel Studio Server Running ===")
    if NOVEL_PATH:
        print(f"Initial Novel: {NOVEL_PATH}")
    if YAML_PATH:
        print(f"Initial YAML : {YAML_PATH}")
    print(f"URL  : http://localhost:{args.port}\n")

    # Start browser auto-opener
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(open_browser(args.port))

    # Start uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
