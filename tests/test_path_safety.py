import os
from pathlib import Path

from src.utils.path_safety import contains_source_segment, is_within


def test_is_within_candidate_inside_base(tmp_path: Path) -> None:
    # 1. baseの配下にあるパスは許可される
    base = tmp_path / "base"
    base.mkdir()
    candidate = base / "sub" / "file.txt"
    assert is_within(base, candidate) is True


def test_is_within_candidate_escapes_via_dotdot(tmp_path: Path) -> None:
    # 2. ../ でbaseの外に脱出するパスは拒否される
    base = tmp_path / "base"
    base.mkdir()
    candidate = base / ".." / "outside" / "secret.txt"
    assert is_within(base, candidate) is False


def test_is_within_rejects_sibling_with_same_prefix(tmp_path: Path) -> None:
    # 3. 文字列としては前方一致するが実際には兄弟ディレクトリであるパスは拒否される
    #    (旧実装の文字列部分一致チェックが誤って許可してしまっていた回帰ケース)
    base = tmp_path / "data" / "sources"
    base.mkdir(parents=True)
    sibling = tmp_path / "data" / "sources_evil" / "x.txt"
    assert is_within(base, sibling) is False


def test_contains_source_segment_true_for_data_sources_path() -> None:
    # 1. data/sources を含むパスはTrue
    path = os.path.join("/", "project", "data", "sources", "plot.txt")
    assert contains_source_segment(path) is True


def test_contains_source_segment_false_for_unrelated_path() -> None:
    # 2. data/sources を含まないパスはFalse
    path = os.path.join("/", "project", "reviews", "1_1", "report.md")
    assert contains_source_segment(path) is False
