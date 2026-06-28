import os
from pathlib import Path

from src.utils.project_paths import (
    DEFAULT_RESULTS_DIR,
    get_findings_yaml_path,
    get_formatted_draft_path,
    get_output_dir,
    get_report_md_path,
    resolve_findings_yaml_path,
    resolve_formatted_draft_path,
)


def test_get_output_dir() -> None:
    assert get_output_dir("test_novel") == os.path.join(
        DEFAULT_RESULTS_DIR, "test_novel"
    )
    assert get_output_dir("test_novel", "custom_dir") == os.path.join(
        "custom_dir", "test_novel"
    )


def test_get_formatted_draft_path() -> None:
    assert get_formatted_draft_path("out_dir", "test_novel") == os.path.join(
        "out_dir", "test_novel_formatted.txt"
    )


def test_resolve_formatted_draft_path(tmp_path: Path) -> None:
    out_dir = str(tmp_path)
    basename = "test_novel"

    # 1. どちらのファイルも存在しない場合、デフォルトのパスが返る
    expected_default = os.path.join(out_dir, f"{basename}_formatted.txt")
    assert resolve_formatted_draft_path(out_dir, basename) == expected_default

    # 2. fallback (01_formatted.txt) だけが存在する場合、fallbackが返る
    fallback_file = tmp_path / "01_formatted.txt"
    fallback_file.touch()
    assert resolve_formatted_draft_path(out_dir, basename) == str(fallback_file)

    # 3. 本来のファイル (basename_formatted.txt) も存在する場合、本来のファイルが優先される
    primary_file = tmp_path / f"{basename}_formatted.txt"
    primary_file.touch()
    assert resolve_formatted_draft_path(out_dir, basename) == str(primary_file)


def test_get_findings_yaml_path() -> None:
    assert get_findings_yaml_path("out_dir", "test_novel") == os.path.join(
        "out_dir", "test_novel_findings.yaml"
    )


def test_resolve_findings_yaml_path(tmp_path: Path) -> None:
    out_dir = str(tmp_path)
    basename = "test_novel"

    # 1. どちらのファイルも存在しない場合、デフォルトのパスが返る
    expected_default = os.path.join(out_dir, f"{basename}_findings.yaml")
    assert resolve_findings_yaml_path(out_dir, basename) == expected_default

    # 2. fallback (00_integrated_findings.yaml) だけが存在する場合、fallbackが返る
    fallback_file = tmp_path / "00_integrated_findings.yaml"
    fallback_file.touch()
    assert resolve_findings_yaml_path(out_dir, basename) == str(fallback_file)

    # 3. 本来のファイル (basename_findings.yaml) も存在する場合、本来のファイルが優先される
    primary_file = tmp_path / f"{basename}_findings.yaml"
    primary_file.touch()
    assert resolve_findings_yaml_path(out_dir, basename) == str(primary_file)


def test_get_report_md_path() -> None:
    assert get_report_md_path("out_dir", "test_novel") == os.path.join(
        "out_dir", "test_novel_report.md"
    )


def test_directory_constants() -> None:
    from src.utils.project_paths import (
        DATA_DIR,
        DATA_SOURCES_DIR,
        NOVELS_DIR,
        SOURCES_DIR,
    )

    assert NOVELS_DIR == "novels"
    assert DATA_DIR == "data"
    assert SOURCES_DIR == "sources"
    assert DATA_SOURCES_DIR == os.path.join("data", "sources")
