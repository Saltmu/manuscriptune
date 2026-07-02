import argparse
import ast
import os
import sys
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# しきい値の定義
LIMIT_PYTHON = 1000
LIMIT_SKILL = 500


class FunctionLineCounter(ast.NodeVisitor):
    """
    Pythonコードを解析し、50行を超える関数・メソッドを検出するNodeVisitorです。
    """

    def __init__(self) -> None:
        self.current_class: list[str] = []
        self.large_functions: list[dict[str, Any]] = []

    def visit_ClassDef(self, node):
        self.current_class.append(node.name)
        self.generic_visit(node)
        self.current_class.pop()

    def visit_FunctionDef(self, node):
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node):
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", start_line)
        length = end_line - start_line + 1
        if length > 50:
            func_name = node.name
            if self.current_class:
                func_name = f"{'.'.join(self.current_class)}.{func_name}"
            self.large_functions.append({"name": func_name, "lines": length})


def analyze_python_file(filepath: Path) -> list[dict[str, Any]]:
    """
    Pythonファイルを解析し、50行を超える関数・メソッドのリストを返します。
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content, filename=str(filepath))
        counter = FunctionLineCounter()
        counter.visit(tree)
        return counter.large_functions
    except Exception as e:
        logger.warning(f"Could not parse Python file {filepath} via AST: {e}")
        return []


def check_file_bloat(filepath: Path, limit: int) -> tuple[bool, int]:
    """
    ファイルの行数をカウントし、しきい値を超えているかを判定します。
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = sum(1 for _ in f)
        return lines > limit, lines
    except Exception as e:
        logger.warning(f"Could not read file {filepath}: {e}")
        return False, 0


def scan_project(root_dir: Path) -> list[dict]:
    """
    プロジェクトを走査し、肥大化したPythonファイルとスキルファイルを検出します。
    """
    reports = []

    # Pythonコードのスキャン (src 配下)
    src_dir = root_dir / "src"
    if src_dir.exists() and src_dir.is_dir():
        for path in src_dir.rglob("*.py"):
            is_bloated, lines = check_file_bloat(path, LIMIT_PYTHON)
            if is_bloated:
                bloated_funcs = analyze_python_file(path)
                reports.append(
                    {
                        "file": path,
                        "lines": lines,
                        "limit": LIMIT_PYTHON,
                        "type": "code",
                        "bloated_functions": bloated_funcs,
                    }
                )

    # スキルのスキャン (skills/**/SKILL.md)
    skills_dir = root_dir / "skills"
    if skills_dir.exists() and skills_dir.is_dir():
        for path in skills_dir.rglob("SKILL.md"):
            is_bloated, lines = check_file_bloat(path, LIMIT_SKILL)
            if is_bloated:
                reports.append(
                    {
                        "file": path,
                        "lines": lines,
                        "limit": LIMIT_SKILL,
                        "type": "skill",
                    }
                )

    return reports


def main():
    parser = argparse.ArgumentParser(
        description="Detect bloated code files and skill definitions."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory of the project to scan.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings but exit with code 0 even if bloat is detected.",
    )
    args = parser.parse_args()

    root_path = Path(args.root).resolve()
    reports = scan_project(root_path)

    if not reports:
        print("No bloated files detected. Clean codebase!")
        sys.exit(0)

    # レポートの出力
    print("\n" + "=" * 60)
    print("                [警告] 肥大化検知レポート")
    print("=" * 60)
    for r in reports:
        rel_path = os.path.relpath(r["file"], root_path)
        print(f"[{'コード' if r['type'] == 'code' else 'スキル'}] {rel_path}")
        print(f"  -> 現在の行数: {r['lines']}行 (しきい値: {r['limit']}行)")
        if r.get("bloated_functions"):
            print("  -> 行数が50行を超える関数/メソッド:")
            for f in r["bloated_functions"]:
                print(f"     - {f['name']}: {f['lines']}行")
        print("-" * 60)

    print("\n上記のファイルはしきい値を超過して肥大化しています。")
    print(
        "モジュールの分割、またはスキルのプロンプト分割等のリファクタリングを推奨します。"
    )
    print("=" * 60 + "\n")

    if args.warn_only:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
