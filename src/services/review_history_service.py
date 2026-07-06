import os
from typing import Any

from src.utils import path_safety, project_paths
from src.utils.yaml_handler import YamlHandler

VERSION_PREFIX = "v"


def _parse_version_number(version_name: str) -> int | None:
    """バージョン名(例: 'v12')から数値部分を抽出する。'v{n}'形式でなければNoneを返す。"""
    if not version_name.startswith(VERSION_PREFIX):
        return None
    suffix = version_name[len(VERSION_PREFIX) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def list_history_versions(basename: str) -> list[dict[str, Any]]:
    """reviews/<basename>/history/v{n}/ 配下の各バージョンのメタ情報一覧を返す。

    バージョン番号の昇順でソートされる。historyディレクトリが存在しない場合は空リストを返す。
    """
    output_dir = project_paths.get_output_dir(basename)
    history_dir = project_paths.get_history_dir(output_dir)

    if not os.path.isdir(history_dir):
        return []

    versions: list[dict[str, Any]] = []
    for entry in os.listdir(history_dir):
        version_number = _parse_version_number(entry)
        if version_number is None:
            continue
        version_dir = os.path.join(history_dir, entry)
        if not os.path.isdir(version_dir):
            continue

        findings_path = os.path.join(version_dir, f"{basename}_findings.yaml")
        report_path = os.path.join(version_dir, f"{basename}_report.md")
        findings = (
            YamlHandler.load_findings(findings_path)
            if os.path.exists(findings_path)
            else []
        )

        versions.append(
            {
                "version": entry,
                "version_number": version_number,
                "mtime": os.path.getmtime(version_dir),
                "findings_count": len(findings),
                "has_report": os.path.exists(report_path),
            }
        )

    versions.sort(key=lambda v: v["version_number"])
    return versions


def get_history_version_detail(basename: str, version: str) -> dict[str, Any]:
    """指定バージョンのreport.md内容・findings.yaml内容を返す。

    historyディレクトリ配下に実際に解決されないパス(パストラバーサル等)や、
    存在しないバージョンが指定された場合はFileNotFoundErrorを送出する。
    """
    output_dir = project_paths.get_output_dir(basename)
    history_dir = project_paths.get_history_dir(output_dir)
    version_dir = project_paths.get_version_dir(output_dir, version)

    if not path_safety.is_within(history_dir, version_dir) or not os.path.isdir(
        version_dir
    ):
        raise FileNotFoundError(
            f"History version '{version}' not found for '{basename}'."
        )

    report_path = os.path.join(version_dir, f"{basename}_report.md")
    findings_path = os.path.join(version_dir, f"{basename}_findings.yaml")

    report_content = ""
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as f:
            report_content = f.read()

    findings = (
        YamlHandler.load_findings(findings_path)
        if os.path.exists(findings_path)
        else []
    )

    return {
        "version": version,
        "report": report_content,
        "findings": findings,
    }
