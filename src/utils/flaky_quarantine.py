from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

DEFAULT_QUARANTINE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "flaky_quarantine.yaml"
)
DEFAULT_RERUNS = 3
DEFAULT_RERUNS_DELAY = 1


def load_quarantined_node_ids(path: Path = DEFAULT_QUARANTINE_PATH) -> set[str]:
    """`flaky_quarantine.yaml`の`tests:`リストを読み込む。

    ファイルが無い/リストが空の場合は空集合を返し、呼び出し側で何もマークしない。
    """
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return set(data.get("tests") or [])


def mark_flaky_items(
    items: Iterable[object],
    quarantined_node_ids: set[str],
    reruns: int = DEFAULT_RERUNS,
    reruns_delay: int = DEFAULT_RERUNS_DELAY,
) -> None:
    """`item.nodeid`が隔離リストに含まれるテストにのみ`pytest.mark.flaky`を付与する。

    quarantine対象外のテストはそのまま（即失敗）にすることで、未知のflaky/
    本物のバグをCI失敗として正しく検知させ続ける。
    """
    if not quarantined_node_ids:
        return
    for item in items:
        if item.nodeid in quarantined_node_ids:  # type: ignore[attr-defined]
            item.add_marker(  # type: ignore[attr-defined]
                pytest.mark.flaky(reruns=reruns, reruns_delay=reruns_delay)
            )
