import asyncio
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.utils import project_paths


def resolve_paths(novel_name: str) -> tuple[str, str]:
    """Resolve novel_path and yaml_path dynamically from a novel filename."""
    if not novel_name:
        raise HTTPException(status_code=400, detail="Novel filename is required.")

    safe_name = os.path.basename(novel_name)
    basename = Path(safe_name).stem

    output_dir = project_paths.get_output_dir(basename)
    formatted_path = os.path.abspath(
        project_paths.resolve_formatted_draft_path(output_dir, basename)
    )

    if os.path.exists(formatted_path):
        novel_path = formatted_path
    else:
        novel_path = os.path.abspath(os.path.join(project_paths.NOVELS_DIR, safe_name))

    yaml_path = os.path.abspath(
        project_paths.resolve_findings_yaml_path(output_dir, basename)
    )
    return novel_path, yaml_path


def render_html_template(template_name: str) -> str:
    """Recursively resolves <!--#include file="filename.html"--> placeholders."""
    template_dir = Path(__file__).parent.parent / "templates"
    template_path = template_dir / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template '{template_name}' not found.")

    with open(template_path, encoding="utf-8") as file:
        content = file.read()

    def replace_match(match):
        include_file = match.group(1)
        return render_html_template(include_file)

    # Pattern to match: <!--#include file="some/path.html"-->
    return re.sub(r'<!--#include file="([^"]+)"-->', replace_match, content)


def stream_process_output(cmd: list[str]) -> StreamingResponse:
    """Runs a command and streams its output via SSE (Server-Sent Events)."""

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
            yield f"data: {line.rstrip()}\n\n"

        rc = await process.wait()
        yield f"data: [PROCESS_EXITED] code={rc}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def rollback_backup(novel_path: str, yaml_path: str) -> dict[str, str]:
    """Restores the backup for a given novel and yaml path."""
    novel_bak = f"{novel_path}.bak"
    yaml_bak = f"{yaml_path}.bak" if yaml_path else None

    if not os.path.exists(novel_bak):
        raise HTTPException(
            status_code=404, detail="Backup file not found. Nothing to rollback."
        )

    try:
        shutil.copy2(novel_bak, novel_path)
        if yaml_bak and os.path.exists(yaml_bak):
            shutil.copy2(yaml_bak, yaml_path)
        elif yaml_path and os.path.exists(yaml_path):
            with open(yaml_path, encoding="utf-8") as file_handle:
                data = yaml.safe_load(file_handle) or {}
            findings = data.get("findings", [])
            for finding in findings:  # Fixed variable collision (f -> finding)
                finding["apply_status"] = None
                finding["apply_result"] = None
            with open(yaml_path, "w", encoding="utf-8") as file_handle:
                yaml.dump(
                    {"findings": findings},
                    file_handle,
                    allow_unicode=True,
                    default_flow_style=False,
                )
        return {"status": "success", "message": "Rollback completed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback: {str(e)}")


def build_writer_cmd(params: Any) -> list[str]:
    """Builds command parameters for running the novel writer CLI."""
    cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "skills/novel-writer-antigravitycli/writer_cli.py",
        "--episode",
        params.episode,
    ]

    if params.model:
        cmd.extend(["--model", params.model])
    if params.novel_title:
        cmd.extend(["--title", params.novel_title])
    if params.policy_global:
        cmd.extend(
            [
                "--policy-global",
                f"{project_paths.DATA_SOURCES_DIR}/{params.policy_global}",
            ]
        )
    if params.policy_chapter:
        cmd.extend(
            [
                "--policy-chapter",
                f"{project_paths.DATA_SOURCES_DIR}/{params.policy_chapter}",
            ]
        )
    if params.character:
        cmd.extend(
            ["--character", f"{project_paths.DATA_SOURCES_DIR}/{params.character}"]
        )
    if params.plot:
        cmd.extend(["--plot-file", f"{project_paths.DATA_SOURCES_DIR}/{params.plot}"])
    if params.step_by_step:
        cmd.append("--step-by-step")
    if params.self_check:
        cmd.append("--self-check")

    return cmd


def shutdown_server():
    """Triggers server shutdown by sending SIGINT."""
    print("[INFO] Shutting down Review Editor server...")
    os.kill(os.getpid(), signal.SIGINT)
