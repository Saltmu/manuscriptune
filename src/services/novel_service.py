import asyncio
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.utils import project_paths
from src.utils.yaml_handler import YamlHandler


def resolve_paths(novel_name: str) -> tuple[str, str]:
    """Resolve novel_path and yaml_path dynamically from a novel filename."""
    if not novel_name:
        raise HTTPException(status_code=400, detail="Novel filename is required.")

    safe_name = os.path.basename(novel_name)
    basename = Path(safe_name).stem.replace("_formatted", "").replace("_findings", "")

    output_dir = project_paths.get_output_dir(basename)
    formatted_path = os.path.abspath(
        project_paths.resolve_formatted_draft_path(output_dir, basename)
    )

    if os.path.exists(formatted_path):
        novel_path = formatted_path
    else:
        novel_path = project_paths.get_novel_path(safe_name)

    yaml_path = os.path.abspath(
        project_paths.resolve_findings_yaml_path(output_dir, basename)
    )
    return novel_path, yaml_path


def render_html_template(template_name: str) -> str:
    """Recursively resolves <!--#include file="filename.html"--> placeholders."""
    template_dir = Path(project_paths.get_templates_dir())
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


def _rollback_versioned(output_dir: str, yaml_path: str, version: str) -> None:
    version_dir = os.path.join(output_dir, "history", version)
    if not os.path.exists(version_dir):
        raise HTTPException(
            status_code=404, detail=f"Backup version '{version}' not found."
        )

    basename = Path(yaml_path).stem.replace("_findings", "")
    bak_yaml = os.path.join(version_dir, f"{basename}_findings.yaml")
    if os.path.exists(bak_yaml):
        shutil.copy2(bak_yaml, yaml_path)

    formatted_txt_path = os.path.abspath(
        project_paths.resolve_formatted_draft_path(output_dir, basename)
    )
    bak_formatted = os.path.join(version_dir, f"{basename}_formatted.txt")
    if os.path.exists(bak_formatted):
        shutil.copy2(bak_formatted, formatted_txt_path)

    bak_report = os.path.join(version_dir, f"{basename}_report.md")
    report_path = os.path.join(output_dir, f"{basename}_report.md")
    if os.path.exists(bak_report):
        shutil.copy2(bak_report, report_path)

    bak_ctx = os.path.join(version_dir, "01_filtered_context.txt")
    ctx_path = os.path.join(output_dir, "01_filtered_context.txt")
    if os.path.exists(bak_ctx):
        shutil.copy2(bak_ctx, ctx_path)

    for fname in os.listdir(version_dir):
        if fname.endswith(".txt") and not fname.endswith("_formatted.txt"):
            original_bak_path = os.path.join(version_dir, fname)
            original_dest_path = os.path.abspath(
                os.path.join(project_paths.NOVELS_DIR, fname)
            )
            shutil.copy2(original_bak_path, original_dest_path)


def rollback_backup(
    novel_path: str, yaml_path: str, version: str | None = None
) -> dict[str, str]:
    """Restores the backup for a given novel and yaml path."""
    if version:
        output_dir = os.path.dirname(yaml_path)
        try:
            _rollback_versioned(output_dir, yaml_path, version)
            return {
                "status": "success",
                "message": f"Rollback to version '{version}' completed successfully.",
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to rollback version '{version}': {str(e)}",
            )

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
            data = YamlHandler.load_safe(yaml_path)
            findings = data.get("findings", [])
            for finding in findings:  # Fixed variable collision (f -> finding)
                finding["apply_status"] = None
                finding["apply_result"] = None
            YamlHandler.dump({"findings": findings}, yaml_path)
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
