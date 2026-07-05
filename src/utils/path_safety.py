import os
from pathlib import Path

from src.utils import project_paths


def is_within(base: str | os.PathLike, candidate: str | os.PathLike) -> bool:
    """candidateがbase配下に実際に解決されるか(..やsymlinkを正規化した上で)を判定する。"""
    base_r = Path(base).resolve()
    try:
        candidate_r = Path(candidate).resolve()
    except (OSError, ValueError):
        return False
    return candidate_r.is_relative_to(base_r)


def contains_source_segment(path: str | os.PathLike) -> bool:
    """正規化した絶対パスの中に、DATA_DIR直後にSOURCES_DIRが来る箇所があるかを判定する。

    save_novel/apply_findings.pyの「data/sources/への書き込み禁止」ガードで共用する。
    """
    parts = Path(os.path.abspath(str(path))).parts
    return any(
        parts[i] == project_paths.DATA_DIR and parts[i + 1] == project_paths.SOURCES_DIR
        for i in range(len(parts) - 1)
    )
