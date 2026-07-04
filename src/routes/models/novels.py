from typing import Any

from pydantic import BaseModel


class FindingItem(BaseModel):
    id: str
    location: str
    original: str
    category: str
    severity: str
    analysis: str
    suggestion: str
    accepted: str
    apply_status: str | None = None
    apply_result: str | None = None
    discussion: list[dict[str, Any]] | None = None
    source_suggestion: dict[str, str] | None = None


class SaveNovelRequest(BaseModel):
    novel_name: str
    content: str


class SaveFindingsRequest(BaseModel):
    novel_name: str
    findings: list[FindingItem]
    metadata: dict[str, Any] | None = None


class SelectFileRequest(BaseModel):
    novel_name: str


class ChatRequest(BaseModel):
    novel_name: str
    finding_id: str
    message: str
    model: str | None = None


class WriteParams(BaseModel):
    episode: str
    novel_title: str | None = None
    policy_global: str | None = None
    policy_chapter: str | None = None
    character: str | None = None
    plot: str | None = None
    model: str | None = None
    step_by_step: bool = False
    self_check: bool = False
    include_neighbor_plots: bool = False


class NovelItem(BaseModel):
    name: str
    size: int
    mtime: str
    has_findings: bool


class NovelListResponse(BaseModel):
    novels: list[NovelItem]


class NovelDetailResponse(BaseModel):
    novel_name: str
    content: str
    findings: list[FindingItem]
    metadata: dict[str, Any] | None = None
    backups: list[str]


class NovelPreviewResponse(BaseModel):
    content: str
    filename: str


class SelectFileResponse(BaseModel):
    status: str
    novel_path: str
    yaml_path: str
    exists: bool


class NovelDataResponse(BaseModel):
    novel_lines: list[str]
    findings: list[FindingItem]
    metadata: dict[str, Any] | None = None
    novel_filename: str
    has_backup: bool
    backups: list[str]


class StatusResponse(BaseModel):
    status: str
    message: str


class WritePromptResponse(BaseModel):
    prompt: str


class ChatResponse(BaseModel):
    status: str
    reply: str
    source_suggestion: dict[str, str] | None = None
