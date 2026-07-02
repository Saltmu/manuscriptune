from unittest.mock import patch

import pytest

from src.utils.detect_bloat import check_file_bloat, main, scan_project


def test_check_file_bloat(tmp_path):
    # しきい値以下のファイル
    small_file = tmp_path / "small.py"
    small_file.write_text("print('hello')\n" * 100, encoding="utf-8")
    assert check_file_bloat(small_file, 1000) == (False, 100)

    # しきい値超過のファイル
    large_file = tmp_path / "large.py"
    large_file.write_text("print('hello')\n" * 1001, encoding="utf-8")
    assert check_file_bloat(large_file, 1000) == (True, 1001)


def test_scan_project(tmp_path):
    # ダミープロジェクト構成を作成
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # OKなPythonファイル
    ok_py = src_dir / "ok.py"
    ok_py.write_text("print('ok')\n" * 900, encoding="utf-8")

    # 肥大化したPythonファイル
    bloated_py = src_dir / "bloated.py"
    bloated_py.write_text("print('bloated')\n" * 1050, encoding="utf-8")

    # OKなSKILL.md
    skill_ok_dir = skills_dir / "ok_skill"
    skill_ok_dir.mkdir()
    skill_ok_md = skill_ok_dir / "SKILL.md"
    skill_ok_md.write_text("instructions\n" * 400, encoding="utf-8")

    # 肥大化したSKILL.md
    skill_bloated_dir = skills_dir / "bloated_skill"
    skill_bloated_dir.mkdir()
    skill_bloated_md = skill_bloated_dir / "SKILL.md"
    skill_bloated_md.write_text("instructions\n" * 550, encoding="utf-8")

    # スキャン実行
    reports = scan_project(root_dir=tmp_path)

    # 検証
    assert len(reports) == 2
    assert any(r["file"].name == "bloated.py" for r in reports)
    assert any(
        r["file"].name == "SKILL.md" and "bloated_skill" in str(r["file"])
        for r in reports
    )


def test_main_exit_codes(tmp_path):
    # ダミープロジェクト構成を作成 (肥大化なし)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    ok_py = src_dir / "ok.py"
    ok_py.write_text("print('ok')", encoding="utf-8")

    # 正常終了の検証
    with patch("sys.argv", ["detect_bloat", "--root", str(tmp_path)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    # 肥大化ありの場合
    bloated_py = src_dir / "bloated.py"
    bloated_py.write_text("print('bloated')\n" * 1050, encoding="utf-8")

    # 異常終了 (終了コード 1) の検証
    with patch("sys.argv", ["detect_bloat", "--root", str(tmp_path)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    # --warn-only フラグありの場合、異常終了せず 0 で終了する検証
    with patch("sys.argv", ["detect_bloat", "--root", str(tmp_path), "--warn-only"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0


def test_scan_project_ast_analysis(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)

    # 50行を超える関数を持つPythonファイルを作成
    content = ["def small_function():", "    return 1", ""]
    content.append("def large_function():")
    for i in range(55):
        content.append(f"    print({i})")
    content.append("")

    # LIMIT_PYTHON(1000)を超えるようにダミーコメントを追加
    dummy_lines = [f"# dummy {i}" for i in range(950)]
    content_large = dummy_lines + content

    bloated_py = src_dir / "bloated_with_large_func.py"
    bloated_py.write_text("\n".join(content_large), encoding="utf-8")

    reports = scan_project(root_dir=tmp_path)

    assert len(reports) == 1
    report = reports[0]
    assert report["file"].name == "bloated_with_large_func.py"
    assert "bloated_functions" in report
    funcs = report["bloated_functions"]
    assert len(funcs) == 1
    assert funcs[0]["name"] == "large_function"
    assert funcs[0]["lines"] == 56  # def (1) + print lines (55)


def test_check_file_bloat_error():
    from pathlib import Path

    is_bloated, lines = check_file_bloat(Path("non_existent_file.py"), 1000)
    assert is_bloated is False
    assert lines == 0


def test_analyze_python_file_parse_error(tmp_path):
    from src.utils.detect_bloat import analyze_python_file

    invalid_py = tmp_path / "invalid.py"
    # SyntaxErrorを誘発するコード
    invalid_py.write_text("if True\n    print('missing colon')", encoding="utf-8")

    funcs = analyze_python_file(invalid_py)
    assert funcs == []
