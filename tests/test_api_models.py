import pytest
from pydantic import ValidationError

from src.routes.models.novels import (
    FindingItem,
    NovelListResponse,
)


def test_finding_item_validation():
    # 必須パラメータがない場合はValidationErrorになるべき
    with pytest.raises(ValidationError):
        FindingItem(id="INT-001")  # locationやoriginalなどが無い

    # 正常系
    item = FindingItem(
        id="INT-001",
        location="1-1",
        original="古い楽器",
        category="logic",
        severity="medium",
        analysis="矛盾",
        suggestion="修正",
        accepted="no",
    )
    assert item.id == "INT-001"


def test_novel_list_response():
    # 正常系
    resp = NovelListResponse(
        novels=[
            {
                "name": "01_novel.txt",
                "size": 1024,
                "mtime": "2026-07-04 12:00:00",
                "has_findings": True,
            }
        ]
    )
    assert len(resp.novels) == 1
    assert resp.novels[0].name == "01_novel.txt"
