from __future__ import annotations

import math
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SIMILARITY_THRESHOLD = 0.2

_RISK_PATH_PATTERNS = (
    re.compile(r"(^|/)data/sources/"),
    re.compile(r"(^|/)credentials/"),
    re.compile(r"(^|/)auth", re.IGNORECASE),
)
_RISK_KEYWORDS = ("subprocess", "auth", "credential")

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class DagCycleError(ValueError):
    """依存関係グラフに循環参照が検出された場合に送出される。"""


@dataclass(frozen=True)
class SubTask:
    id: str
    description: str
    footprint: tuple[str, ...]
    symbols: tuple[str, ...]
    depends_on: tuple[str, ...]
    risk: bool
    risk_reasons: tuple[str, ...]

    def touch_set(self) -> frozenset[str]:
        return frozenset(self.footprint) | frozenset(self.symbols)


@dataclass(frozen=True)
class DagEdge:
    source: str
    target: str
    reason: str
    score: float | None = None


@dataclass(frozen=True)
class DagResult:
    subtasks: dict[str, SubTask]
    edges: list[DagEdge]
    topological_order: list[str]
    parallel_leaves: list[str]
    risky_subtask_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtasks": {
                subtask_id: {
                    "description": s.description,
                    "footprint": list(s.footprint),
                    "symbols": list(s.symbols),
                    "depends_on": list(s.depends_on),
                    "risk": s.risk,
                    "risk_reasons": list(s.risk_reasons),
                }
                for subtask_id, s in self.subtasks.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "reason": e.reason,
                    "score": e.score,
                }
                for e in self.edges
            ],
            "topological_order": list(self.topological_order),
            "parallel_leaves": list(self.parallel_leaves),
            "risky_subtask_ids": list(self.risky_subtask_ids),
        }


@dataclass(frozen=True)
class FootprintConflict:
    subtask_id: str
    other_subtask_id: str
    similarity: float
    blocked_subtask_id: str


def _detect_risk_from_values(
    footprint: Iterable[str],
    symbols: Iterable[str],
    description: str,
    explicit: bool = False,
) -> tuple[bool, tuple[str, ...]]:
    footprint = tuple(footprint)
    symbols = tuple(symbols)
    reasons: list[str] = []

    for path_str in footprint:
        for pattern in _RISK_PATH_PATTERNS:
            if pattern.search(path_str):
                reasons.append(f"footprint:{path_str}")
                break

    haystack = " ".join([*footprint, *symbols, description]).lower()
    for keyword in _RISK_KEYWORDS:
        if keyword in haystack:
            reasons.append(f"keyword:{keyword}")

    if explicit:
        reasons.append("explicit")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return bool(unique_reasons), unique_reasons


def _extract_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        raise ValueError(
            "decomposition_plan.md にYAMLフロントマター（--- ... ---）が見つかりません"
        )
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("フロントマターの内容がマッピング形式ではありません")
    return data


def parse_decomposition_plan(path: str | Path) -> list[SubTask]:
    """decomposition_plan.md のYAMLフロントマターをパースし、SubTaskの一覧を返す。"""
    text = Path(path).read_text(encoding="utf-8")
    data = _extract_frontmatter(text)

    raw_subtasks = data.get("subtasks")
    if not isinstance(raw_subtasks, list) or not raw_subtasks:
        raise ValueError("subtasks が定義されていないか、空です")

    subtasks: list[SubTask] = []
    seen_ids: set[str] = set()
    for raw in raw_subtasks:
        subtask_id = str(raw["id"])
        if subtask_id in seen_ids:
            raise ValueError(f"サブタスクIDが重複しています: {subtask_id}")
        seen_ids.add(subtask_id)

        footprint = tuple(str(f) for f in raw.get("footprint", []) or [])
        symbols = tuple(str(s) for s in raw.get("symbols", []) or [])
        depends_on = tuple(str(d) for d in raw.get("depends_on", []) or [])
        description = str(raw.get("description", ""))

        risk, risk_reasons = _detect_risk_from_values(
            footprint, symbols, description, explicit=bool(raw.get("risk", False))
        )

        subtasks.append(
            SubTask(
                id=subtask_id,
                description=description,
                footprint=footprint,
                symbols=symbols,
                depends_on=depends_on,
                risk=risk,
                risk_reasons=risk_reasons,
            )
        )

    known_ids = {s.id for s in subtasks}
    for s in subtasks:
        unknown = [d for d in s.depends_on if d not in known_ids]
        if unknown:
            raise ValueError(f"未知のdepends_onが指定されています: {s.id} -> {unknown}")

    return subtasks


def _otsuka_ochiai(set_a: frozenset[str], set_b: frozenset[str]) -> float:
    """Otsuka-Ochiai係数によるコサイン類似度: |Si∩Sj| / sqrt(|Si|・|Sj|)。"""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    if intersection == 0:
        return 0.0
    return intersection / math.sqrt(len(set_a) * len(set_b))


def _find_candidate_pairs(subtasks: list[SubTask]) -> set[tuple[str, str]]:
    """一次探索: 共有ファイル/シンボル単位の軽量な逆引きインデックスから、
    交差が非ゼロになり得るペアだけを安価に絞り込む（総当りO(n^2)を回避）。"""
    inverted_index: dict[str, list[str]] = {}
    for subtask in subtasks:
        for item in subtask.touch_set():
            inverted_index.setdefault(item, []).append(subtask.id)

    candidates: set[tuple[str, str]] = set()
    for ids_sharing_item in inverted_index.values():
        if len(ids_sharing_item) < 2:
            continue
        for i, a in enumerate(ids_sharing_item):
            for b in ids_sharing_item[i + 1 :]:
                if a != b:
                    candidates.add(tuple(sorted((a, b))))  # type: ignore[arg-type]
    return candidates


def build_similarity_edges(
    subtasks: list[SubTask], threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> list[DagEdge]:
    """二次探索: 一次探索の候補ペアに対してのみ、精緻な結合度スコアを算出する。"""
    by_id = {s.id: s for s in subtasks}
    edges: list[DagEdge] = []
    for a_id, b_id in sorted(_find_candidate_pairs(subtasks)):
        score = _otsuka_ochiai(by_id[a_id].touch_set(), by_id[b_id].touch_set())
        if score > threshold:
            edges.append(
                DagEdge(source=a_id, target=b_id, reason="similarity", score=score)
            )
    return edges


def _collect_explicit_edges(subtasks: list[SubTask]) -> list[DagEdge]:
    edges: list[DagEdge] = []
    for subtask in subtasks:
        for dep_id in subtask.depends_on:
            edges.append(DagEdge(source=dep_id, target=subtask.id, reason="explicit"))
    return edges


def _merge_explicit_and_similarity(
    explicit_edges: list[DagEdge], similarity_edges: list[DagEdge]
) -> list[DagEdge]:
    explicit_pairs = {(e.source, e.target) for e in explicit_edges}
    merged = list(explicit_edges)
    for edge in similarity_edges:
        if (edge.source, edge.target) in explicit_pairs:
            continue
        if (edge.target, edge.source) in explicit_pairs:
            continue
        merged.append(edge)
    return merged


def _detect_cycle(node_ids: list[str], edges: list[DagEdge]) -> list[str] | None:
    """DFSによる循環参照検出。循環があればその経路を、なければNoneを返す。"""
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        graph[edge.source].append(edge.target)

    white, gray, black = 0, 1, 2
    color = dict.fromkeys(node_ids, white)
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = gray
        path.append(node)
        for neighbor in graph[node]:
            if color[neighbor] == gray:
                cycle_start = path.index(neighbor)
                return [*path[cycle_start:], neighbor]
            if color[neighbor] == white:
                found = visit(neighbor)
                if found:
                    return found
        path.pop()
        color[node] = black
        return None

    for node_id in node_ids:
        if color[node_id] == white:
            cycle = visit(node_id)
            if cycle:
                return cycle
    return None


def _topological_sort(node_ids: list[str], edges: list[DagEdge]) -> list[str]:
    in_degree = dict.fromkeys(node_ids, 0)
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        graph[edge.source].append(edge.target)
        in_degree[edge.target] += 1

    queue: deque[str] = deque(sorted(n for n in node_ids if in_degree[n] == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in sorted(graph[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(node_ids):
        raise DagCycleError("トポロジカルソートに失敗しました（循環参照が疑われます）")
    return order


def _assemble_dag(
    subtask_list: list[SubTask], merged_edges: list[DagEdge]
) -> DagResult:
    node_ids = [s.id for s in subtask_list]

    cycle = _detect_cycle(node_ids, merged_edges)
    if cycle:
        raise DagCycleError(f"循環参照を検出しました: {' -> '.join(cycle)}")

    topological_order = _topological_sort(node_ids, merged_edges)

    in_degree = dict.fromkeys(node_ids, 0)
    for edge in merged_edges:
        in_degree[edge.target] += 1
    parallel_leaves = sorted(n for n in node_ids if in_degree[n] == 0)

    risky_subtask_ids = sorted(s.id for s in subtask_list if s.risk)

    return DagResult(
        subtasks={s.id: s for s in subtask_list},
        edges=merged_edges,
        topological_order=topological_order,
        parallel_leaves=parallel_leaves,
        risky_subtask_ids=risky_subtask_ids,
    )


def build_dag(
    subtasks: list[SubTask], threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> DagResult:
    """明示的依存 + 結合度スコアによる依存を統合し、DAGを構築する。

    循環参照が見つかった場合は DagCycleError を送出する。
    """
    explicit_edges = _collect_explicit_edges(subtasks)
    similarity_edges = build_similarity_edges(subtasks, threshold=threshold)
    merged_edges = _merge_explicit_and_similarity(explicit_edges, similarity_edges)
    return _assemble_dag(subtasks, merged_edges)


def build_dag_from_plan(
    path: str | Path, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> dict[str, Any]:
    """decomposition_plan.md のパスを受け取り、DAG構造(JSON互換dict)を返す単純な入出力。

    #187のドラフト呼び出し導線から薄いラッパーとして呼び出される想定のため、
    入出力はこの1関数（パス文字列 -> dict）のみで完結する。
    """
    subtasks = parse_decomposition_plan(path)
    dag = build_dag(subtasks, threshold=threshold)
    return dag.to_dict()


def recompute_dag_for_footprint_change(
    subtasks: dict[str, SubTask],
    subtask_id: str,
    updated_footprint: Iterable[str] | None = None,
    updated_symbols: Iterable[str] | None = None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[DagResult, list[FootprintConflict]]:
    """実行中サブタスクのfootprint逸脱を反映してDAGを再計算する。

    設計判断: 新たに検出された結合度エッジ（衝突ペア）は、既に実行が
    始まっている `subtask_id` 側を優先し、相手側のサブタスクを直列化
    （待機）させる方向で辺を張る。どちらも未実行の状態から新規に競合が
    発覚するケースでは「先に走り出した側が優先される」という単純な
    ルールの方が、通知・記録（#184）側で扱いやすいと判断した。
    また、一度リスクフラグが立ったサブタスクは、再計算後も安全側に倒し
    リスクフラグを保持し続ける（モノトニックに扱う）。
    """
    if subtask_id not in subtasks:
        raise KeyError(f"未知のサブタスクIDです: {subtask_id}")

    before_similarity_pairs = {
        frozenset((e.source, e.target))
        for e in build_similarity_edges(list(subtasks.values()), threshold=threshold)
    }

    old_subtask = subtasks[subtask_id]
    new_footprint = (
        tuple(updated_footprint)
        if updated_footprint is not None
        else old_subtask.footprint
    )
    new_symbols = (
        tuple(updated_symbols) if updated_symbols is not None else old_subtask.symbols
    )

    heuristic_risk, heuristic_reasons = _detect_risk_from_values(
        new_footprint, new_symbols, old_subtask.description
    )
    combined_risk = old_subtask.risk or heuristic_risk
    combined_reasons = tuple(
        dict.fromkeys([*old_subtask.risk_reasons, *heuristic_reasons])
    )

    new_subtask = SubTask(
        id=old_subtask.id,
        description=old_subtask.description,
        footprint=new_footprint,
        symbols=new_symbols,
        depends_on=old_subtask.depends_on,
        risk=combined_risk,
        risk_reasons=combined_reasons,
    )

    updated_subtasks = dict(subtasks)
    updated_subtasks[subtask_id] = new_subtask
    subtask_list = list(updated_subtasks.values())

    explicit_edges = _collect_explicit_edges(subtask_list)
    explicit_pairs = {(e.source, e.target) for e in explicit_edges}
    similarity_edges = build_similarity_edges(subtask_list, threshold=threshold)

    conflicts: list[FootprintConflict] = []
    final_similarity_edges: list[DagEdge] = []
    for edge in similarity_edges:
        pair_key = frozenset((edge.source, edge.target))
        if (edge.source, edge.target) in explicit_pairs or (
            edge.target,
            edge.source,
        ) in explicit_pairs:
            continue  # 明示的な依存が既にあるため、新規の衝突として扱わない

        is_new = pair_key not in before_similarity_pairs
        if is_new and subtask_id in pair_key:
            other_id = edge.target if edge.source == subtask_id else edge.source
            final_similarity_edges.append(
                DagEdge(
                    source=subtask_id,
                    target=other_id,
                    reason="similarity",
                    score=edge.score,
                )
            )
            conflicts.append(
                FootprintConflict(
                    subtask_id=subtask_id,
                    other_subtask_id=other_id,
                    similarity=edge.score or 0.0,
                    blocked_subtask_id=other_id,
                )
            )
        else:
            final_similarity_edges.append(edge)

    merged_edges = explicit_edges + final_similarity_edges
    result = _assemble_dag(subtask_list, merged_edges)
    return result, conflicts
