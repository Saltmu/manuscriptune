import os

from src.run_review_pipeline import (
    _resolve_output_dir,
    archive_previous_review,
)


def test_resolve_output_dir(tmp_path):
    target_file = tmp_path / "novels" / "episode_1.txt"
    os.makedirs(target_file.parent, exist_ok=True)
    target_file.touch()

    # Case 1: dir is None, output directory defaults to novel_check_results/{basename}
    basename, output_dir = _resolve_output_dir(target_file, None)
    assert basename == "episode_1"
    assert output_dir == os.path.join("novel_check_results", "episode_1")

    # Case 2: dir is specified
    custom_dir = str(tmp_path / "custom_results")
    basename, output_dir = _resolve_output_dir(target_file, custom_dir)
    assert basename == "episode_1"
    assert output_dir == custom_dir


def test_archive_previous_review(tmp_path):
    basename = "episode_1"
    output_dir = tmp_path / "novel_check_results" / basename
    os.makedirs(output_dir, exist_ok=True)

    # Place mock files to archive
    formatted_txt = output_dir / f"{basename}_formatted.txt"
    findings_yaml = output_dir / f"{basename}_findings.yaml"
    report_md = output_dir / f"{basename}_report.md"
    filtered_ctx = output_dir / "01_filtered_context.txt"

    formatted_txt.write_text("formatted text contents", encoding="utf-8")
    findings_yaml.write_text("findings yaml contents", encoding="utf-8")
    report_md.write_text("report markdown contents", encoding="utf-8")
    filtered_ctx.write_text("filtered context contents", encoding="utf-8")

    # Perform first archive
    archive_previous_review(str(output_dir), basename)

    # Verify history directory and archived files
    history_dir = output_dir / "history"
    assert os.path.exists(history_dir)
    assert os.path.exists(history_dir / f"v1_{basename}_formatted.txt")
    assert os.path.exists(history_dir / f"v1_{basename}_findings.yaml")
    assert os.path.exists(history_dir / f"v1_{basename}_report.md")
    assert os.path.exists(history_dir / "v1_filtered_context.txt")

    # Perform second archive (recreate findings file so archive isn't skipped)
    findings_yaml.write_text("findings yaml contents v2", encoding="utf-8")
    archive_previous_review(str(output_dir), basename)
    assert os.path.exists(history_dir / f"v2_{basename}_formatted.txt")
