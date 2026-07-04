import datetime
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from src.services import novel_service
from src.utils import plot_parser, project_paths
from src.utils import project_config as writer_helper
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

router = APIRouter()
logger = get_logger(__name__)


@router.get("/api/plots")
async def list_plots():
    sources_dir = Path(project_paths.get_sources_dir())
    if not sources_dir.exists():
        return {"plots": []}

    plots_list = []
    for f in sorted(sources_dir.glob("*.txt"), key=writer_helper.natural_sort_key):
        name = f.name
        if "プロット" in name or "plot" in name.lower() or name == "第1幕概要.txt":
            plot_stem = f.stem
            yaml_path = project_paths.get_plot_findings_yaml_path(
                project_paths.get_output_dir(plot_stem), plot_stem
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
    plot_path = project_paths.get_source_path(safe_file)
    if not os.path.exists(plot_path):
        raise HTTPException(status_code=404, detail="Plot file not found.")

    with open(plot_path, encoding="utf-8") as f:
        content = f.read()

    plot_stem = Path(plot_path).stem
    yaml_path = project_paths.get_plot_findings_yaml_path(
        project_paths.get_output_dir(plot_stem), plot_stem
    )
    findings = []
    if os.path.exists(yaml_path):
        try:
            data = YamlHandler.load_safe(yaml_path)
            if data and "findings" in data:
                findings = data["findings"]
        except Exception as e:
            logger.error(f"Error reading plot YAML findings: {e}", exc_info=True)

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
    plot_path = project_paths.get_source_path(safe_file)
    if not os.path.exists(plot_path):
        raise HTTPException(status_code=404, detail="Plot file not found.")

    cmd = [
        "poetry",
        "run",
        "python",
        "-u",
        "src/cli/run_plot_review_pipeline.py",
        plot_path,
    ]
    if model:
        cmd.extend(["--model", model])

    return novel_service.stream_process_output(cmd)


def kanji_to_num(kanji_str: str) -> int:
    kanji_dict = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if not kanji_str:
        return 0
    if kanji_str.isdigit():
        return int(kanji_str)
    if len(kanji_str) == 1:
        return kanji_dict.get(kanji_str, 0)

    res = 0
    if "十" in kanji_str:
        parts = kanji_str.split("十")
        res += kanji_dict.get(parts[0], 0) * 10 if parts[0] else 10
        if parts[1]:
            res += kanji_dict.get(parts[1], 0)
    else:
        digits = re.findall(r"\d+", kanji_str)
        if digits:
            res = int(digits[0])
    return res


def extract_number(title: str) -> int:
    match = re.search(r"(?:第|幕間)([一二三四五六七八九十0-9]+)(?:章|話)?", title)
    if not match:
        return 0
    val = match.group(1)
    if val.isdigit():
        return int(val)
    return kanji_to_num(val)


def _resolve_episode_status(matched_file: str | None) -> tuple[str, int]:
    if not matched_file:
        return "unwritten", 0

    try:
        _, yaml_path = novel_service.resolve_paths(matched_file)
        if yaml_path and os.path.exists(yaml_path):
            status = "reviewed"
            findings_count = 0
            try:
                data = YamlHandler.load_safe(yaml_path)
                if isinstance(data, dict):
                    findings_count = len(data.get("findings", []))
                elif isinstance(data, list):
                    findings_count = len(data)
            except Exception:
                pass
            return status, findings_count
        else:
            return "written", 0
    except Exception:
        return "written", 0


@router.get("/api/plot/episodes_status")
async def get_plot_episodes_status(
    file: str = Query(..., description="Plot filename in sources/"),
):
    safe_file = os.path.basename(file)
    plot_path = project_paths.get_source_path(safe_file)
    if not os.path.exists(plot_path):
        raise HTTPException(status_code=404, detail="Plot file not found.")

    # Parse plot structure
    chapters_struct = plot_parser.parse_plot(plot_path)

    # List files in novels directory
    novels_dir = project_paths.get_novels_dir()
    novel_files = []
    if os.path.exists(novels_dir):
        novel_files = [f for f in os.listdir(novels_dir) if f.endswith(".txt")]

    result_chapters = []
    for ch in chapters_struct:
        ch_num = extract_number(ch["title"])
        episodes_status = []
        for ep in ch["episodes"]:
            ep_num = extract_number(ep["title"])

            # Try to match a novel file like ch_num_ep_num
            matched_file = None
            if ch_num > 0 and ep_num > 0:
                pattern = re.compile(rf"^{ch_num}_{ep_num}(?:\D|$)")
                for nf in novel_files:
                    if pattern.match(nf):
                        matched_file = nf
                        break

            status, findings_count = _resolve_episode_status(matched_file)

            episodes_status.append(
                {
                    "title": ep["title"],
                    "name": ep["name"],
                    "status": status,
                    "novel_file": matched_file,
                    "findings_count": findings_count,
                }
            )

        result_chapters.append(
            {"title": ch["title"], "name": ch["name"], "episodes": episodes_status}
        )

    return {"chapters": result_chapters}
