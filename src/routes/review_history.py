import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from src.routes.models.review_history import (
    ReviewHistoryDetailResponse,
    ReviewHistoryListResponse,
)
from src.services import review_history_service

router = APIRouter()


@router.get("/api/review_history", response_model=ReviewHistoryListResponse)
async def list_review_history(
    file: str = Query(..., description="Novel/episode filename"),
):
    basename = Path(os.path.basename(file)).stem
    versions = review_history_service.list_history_versions(basename)
    return {"versions": versions}


@router.get("/api/review_history/detail", response_model=ReviewHistoryDetailResponse)
async def get_review_history_detail(
    file: str = Query(..., description="Novel/episode filename"),
    version: str = Query(..., description="History version, e.g. 'v1'"),
):
    basename = Path(os.path.basename(file)).stem
    try:
        return review_history_service.get_history_version_detail(basename, version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
