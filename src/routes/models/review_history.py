from typing import Any

from pydantic import BaseModel


class ReviewHistoryVersionItem(BaseModel):
    version: str
    version_number: int
    mtime: float
    findings_count: int
    has_report: bool


class ReviewHistoryListResponse(BaseModel):
    versions: list[ReviewHistoryVersionItem]


class ReviewHistoryDetailResponse(BaseModel):
    version: str
    report: str
    findings: list[Any]
