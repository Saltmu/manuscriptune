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

from src.utils import plot_parser, project_config, project_paths
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)


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
        logger.info(f"Running process stream: {' '.join(cmd)}")
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
    if params.include_neighbor_plots:
        cmd.append("--include-neighbor-plots")

    return cmd


def shutdown_server():
    """Triggers server shutdown by sending SIGINT."""
    logger.info("Shutting down Review Editor server...")
    os.kill(os.getpid(), signal.SIGINT)


def archive_current_state(
    basename: str,
    extra_novel_path: str | None = None,
    output_dir: str | None = None,
) -> str:
    """現在の小説テキストとレビュー関連ファイルを reviews/{basename}/history/v{version}/ に退避する。"""
    if not output_dir:
        output_dir = project_paths.get_output_dir(basename)
    history_dir = project_paths.get_history_dir(output_dir)
    os.makedirs(history_dir, exist_ok=True)

    # 次のバージョン番号を決定
    existing_versions = []
    version_pattern = re.compile(r"^v(\d+)$")
    for d in os.listdir(history_dir):
        if os.path.isdir(os.path.join(history_dir, d)):
            match = version_pattern.match(d)
            if match:
                existing_versions.append(int(match.group(1)))

    next_version = max(existing_versions) + 1 if existing_versions else 1
    v_prefix = f"v{next_version}"
    version_dir = project_paths.get_version_dir(output_dir, v_prefix)
    os.makedirs(version_dir, exist_ok=True)

    logger.info(f"Archiving current state of {basename} to history/{v_prefix}/...")

    # コピー対象ファイルの定義 (reviews/{basename} 配下の主要ファイルを退避)
    formatted_txt_path = project_paths.resolve_formatted_draft_path(
        output_dir, basename
    )
    yaml_path = project_paths.resolve_findings_yaml_path(output_dir, basename)
    report_path = project_paths.get_report_md_path(output_dir, basename)
    ctx_path = project_paths.get_filtered_context_path(output_dir)

    files_to_copy = []
    if os.path.exists(formatted_txt_path):
        files_to_copy.append((formatted_txt_path, os.path.basename(formatted_txt_path)))
    if os.path.exists(yaml_path):
        files_to_copy.append((yaml_path, os.path.basename(yaml_path)))
    if os.path.exists(report_path):
        files_to_copy.append((report_path, os.path.basename(report_path)))
    if os.path.exists(ctx_path):
        files_to_copy.append((ctx_path, os.path.basename(ctx_path)))

    # 小説原本ファイル
    if extra_novel_path and os.path.exists(extra_novel_path):
        files_to_copy.append((extra_novel_path, os.path.basename(extra_novel_path)))

    # コピー実行
    for src, dest_name in files_to_copy:
        shutil.copy2(src, os.path.join(version_dir, dest_name))
        logger.info(
            f"Archived: {os.path.basename(src)} -> history/{v_prefix}/{dest_name}"
        )

    return v_prefix


def resolve_novel_path_for_write(
    episode: str, plot_file: str | None = None
) -> tuple[str, str]:
    """エピソード名（例：「第1話」）とプロットファイルから、小説ファイルの絶対パスと basename を解決する。"""
    plot_filepath = (
        plot_file
        if plot_file
        else project_config.resolve_novel_file_by_pattern(
            "plot", "*第1幕プロット*.txt", "data/sources/04_1_第1幕プロットver.3.0.txt"
        )
    )

    # data/sources ディレクトリからのパス解決
    if not os.path.isabs(plot_filepath):
        plot_filepath = os.path.abspath(
            project_paths.get_source_path(os.path.basename(plot_filepath))
        )

    # プロットデータのパース
    plot_data = plot_parser.parse_plot(plot_filepath)

    chapter_title = None
    for chapter_data in plot_data:
        c_title = chapter_data.get("title", "")
        for ep in chapter_data.get("episodes", []):
            if (
                ep["title"] == episode
                or episode in ep["title"]
                or episode in ep["name"]
            ):
                chapter_title = c_title
                break
        if chapter_title:
            break

    # 番号抽出
    def extract_numbers(text):
        match = re.search(r"\d+", text)
        return match.group(0) if match else "0"

    ch_num = extract_numbers(chapter_title) if chapter_title else "0"
    ep_num = extract_numbers(episode)
    basename = f"{ch_num}_{ep_num}"
    novel_path = os.path.abspath(project_paths.get_novel_path(f"{basename}.txt"))
    return novel_path, basename
