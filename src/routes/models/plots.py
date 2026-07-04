from pydantic import BaseModel


class PlotItem(BaseModel):
    name: str
    size: int
    mtime: str
    has_findings: bool


class PlotListResponse(BaseModel):
    plots: list[PlotItem]


class PlotDetailResponse(BaseModel):
    plot_name: str
    content: str
    findings: list[dict]


class EpisodeStatusItem(BaseModel):
    title: str
    name: str
    status: str
    novel_file: str | None = None
    findings_count: int


class ChapterStatusItem(BaseModel):
    title: str
    name: str
    episodes: list[EpisodeStatusItem]


class PlotEpisodesStatusResponse(BaseModel):
    chapters: list[ChapterStatusItem]
