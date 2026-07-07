from unittest.mock import patch

import pytest

from src.services import review_history_service


def _setup_history(tmp_path, basename):
    output_dir = tmp_path / "reviews" / basename
    output_dir.mkdir(parents=True)
    return output_dir


def _write_version(
    output_dir, basename, version, *, findings_count=0, with_report=True
):
    version_dir = output_dir / "history" / version
    version_dir.mkdir(parents=True)

    findings = [{"id": f"F-{i}"} for i in range(findings_count)]
    (version_dir / f"{basename}_findings.yaml").write_text(
        "findings:\n" + "".join(f"  - id: F-{i}\n" for i in range(findings_count))
        if findings_count
        else "findings: []",
        encoding="utf-8",
    )
    if with_report:
        (version_dir / f"{basename}_report.md").write_text(
            f"# Report {version}", encoding="utf-8"
        )
    return version_dir, findings


def test_list_history_versions_returns_sorted_metadata(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v2", findings_count=1)
    _write_version(output_dir, basename, "v1", findings_count=3, with_report=False)
    _write_version(output_dir, basename, "v10", findings_count=0)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        versions = review_history_service.list_history_versions(basename)

    assert [v["version"] for v in versions] == ["v1", "v2", "v10"]

    v1 = versions[0]
    assert v1["findings_count"] == 3
    assert v1["has_report"] is False
    assert "mtime" in v1

    v2 = versions[1]
    assert v2["findings_count"] == 1
    assert v2["has_report"] is True


def test_list_history_versions_no_history_dir_returns_empty_list(tmp_path):
    basename = "no_history"
    output_dir = _setup_history(tmp_path, basename)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        versions = review_history_service.list_history_versions(basename)

    assert versions == []


def test_list_history_versions_ignores_non_version_entries(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v1", findings_count=0)
    history_dir = output_dir / "history"
    (history_dir / "not_a_version.txt").write_text("stray", encoding="utf-8")
    # 'v'で始まるが数値でないサフィックス
    (history_dir / "vlatest").write_text("stray", encoding="utf-8")
    # 'v{n}'形式だがディレクトリではなくファイル
    (history_dir / "v99").write_text("stray", encoding="utf-8")

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        versions = review_history_service.list_history_versions(basename)

    assert [v["version"] for v in versions] == ["v1"]


def test_get_history_version_detail_returns_report_and_findings(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v1", findings_count=2)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        detail = review_history_service.get_history_version_detail(basename, "v1")

    assert detail["version"] == "v1"
    assert detail["report"] == "# Report v1"
    assert len(detail["findings"]) == 2


def test_get_history_version_detail_missing_report_returns_empty_string(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v1", findings_count=0, with_report=False)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        detail = review_history_service.get_history_version_detail(basename, "v1")

    assert detail["report"] == ""
    assert detail["findings"] == []


def test_get_history_version_detail_missing_version_raises(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v1", findings_count=0)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        with pytest.raises(FileNotFoundError):
            review_history_service.get_history_version_detail(basename, "v99")


def test_get_history_version_detail_missing_history_dir_raises(tmp_path):
    basename = "no_history"
    output_dir = _setup_history(tmp_path, basename)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        with pytest.raises(FileNotFoundError):
            review_history_service.get_history_version_detail(basename, "v1")


def test_get_history_version_detail_rejects_path_traversal(tmp_path):
    basename = "1_12"
    output_dir = _setup_history(tmp_path, basename)
    _write_version(output_dir, basename, "v1", findings_count=0)

    with patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)):
        with pytest.raises(FileNotFoundError):
            review_history_service.get_history_version_detail(basename, "../../etc")
