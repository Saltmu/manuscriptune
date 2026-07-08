from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]*$")
_REF_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")


def _validate_issue_number(value: int | str) -> int:
    text = str(value)
    if not re.fullmatch(r"[0-9]+", text) or int(text) <= 0:
        raise ValueError(f"issue番号が不正です: {value!r}")
    return int(text)


def _validate_label(label: str) -> str:
    if not label or not _LABEL_PATTERN.match(label):
        raise ValueError(f"ラベル名が不正です: {label!r}")
    return label


def _validate_ref_name(ref: str) -> str:
    if (
        not ref
        or not _REF_NAME_PATTERN.match(ref)
        or ref.startswith("-")
        or ".." in ref
    ):
        raise ValueError(f"ブランチ名が不正です: {ref!r}")
    return ref


@dataclass(frozen=True)
class IssueRecord:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    created_at: str


@dataclass(frozen=True)
class PrRecord:
    number: int
    head_ref: str
    changed_files: tuple[str, ...]
    closes_issue_numbers: tuple[int, ...] = ()
    review_decision: str = ""
    is_ci_passing: bool = True


def _run(args: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


_VALID_ISSUE_STATES = frozenset({"open", "closed", "all"})


def list_issues_by_label(label: str, state: str = "open") -> list[IssueRecord]:
    """#236: `state`を明示指定できるようにする。既定は従来通り`open`のみ。

    `status:done`昇格判定は、人間が完了Issueを通常のGitHub運用でClose
    した場合でも依存解決できるよう、呼び出し側から`state="all"`を
    渡してclosedなIssueも含めて検索できる。
    """
    _validate_label(label)
    if state not in _VALID_ISSUE_STATES:
        raise ValueError(f"stateが不正です: {state!r}")
    stdout = _run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            label,
            "--state",
            state,
            "--json",
            "number,title,body,labels,createdAt",
        ]
    )
    raw_issues = json.loads(stdout)
    return [
        IssueRecord(
            number=raw["number"],
            title=raw["title"],
            body=raw["body"],
            labels=tuple(entry["name"] for entry in raw.get("labels", [])),
            created_at=raw["createdAt"],
        )
        for raw in raw_issues
    ]


def add_label(issue_number: int | str, label: str) -> None:
    number = _validate_issue_number(issue_number)
    _validate_label(label)
    _run(["gh", "issue", "edit", str(number), "--add-label", label])


def remove_label(issue_number: int | str, label: str) -> None:
    number = _validate_issue_number(issue_number)
    _validate_label(label)
    _run(["gh", "issue", "edit", str(number), "--remove-label", label])


def add_comment(issue_number: int | str, body: str) -> None:
    number = _validate_issue_number(issue_number)
    _run(["gh", "issue", "comment", str(number), "--body-file", "-"], input_text=body)


def get_issue_labels(issue_number: int | str) -> tuple[str, ...]:
    """#186: 統合コーディネーターの意味的レビュー結果（合否ラベル）をポーリングするために使う。"""
    number = _validate_issue_number(issue_number)
    stdout = _run(["gh", "issue", "view", str(number), "--json", "labels"])
    raw = json.loads(stdout)
    return tuple(entry["name"] for entry in raw.get("labels", []))


_VALID_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})


def merge_pr(pr_number: int | str, merge_method: str = "merge") -> None:
    """#186: 意味的レビュー通過後、Python側が決定論的にサブタスクPRをマージする。

    このリポジトリの慣習（通常のマージコミット、squashではない）に合わせ、
    既定は`--merge`。マージ後はブランチを削除する。
    """
    number = _validate_issue_number(pr_number)
    if merge_method not in _VALID_MERGE_METHODS:
        raise ValueError(f"merge_methodが不正です: {merge_method!r}")
    _run(["gh", "pr", "merge", str(number), f"--{merge_method}", "--delete-branch"])


def list_remote_branches() -> list[str]:
    stdout = _run(["git", "branch", "-r", "--format=%(refname:short)"])
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def list_open_prs() -> list[PrRecord]:
    """#239: ブランチ名がAIセッションの指示通りにならない場合でも自己PRと
    判定できるよう、`closingIssuesReferences`（`Closes #N`等から解決される
    GitHub側の正規のIssue参照一覧）も併せて取得する。"""
    stdout = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,headRefName,reviewDecision,statusCheckRollup",
        ]
    )
    raw_prs = json.loads(stdout)
    prs: list[PrRecord] = []
    for raw in raw_prs:
        number = raw["number"]
        detail_stdout = _run(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--json",
                "files,closingIssuesReferences",
            ]
        )
        detail = json.loads(detail_stdout)
        files = detail.get("files", [])
        closing_refs = detail.get("closingIssuesReferences", [])

        rollup = raw.get("statusCheckRollup") or []
        is_ci_passing = True
        for check in rollup:
            status = check.get("status")
            conclusion = check.get("conclusion")
            if status != "COMPLETED" or conclusion not in (
                "SUCCESS",
                "NEUTRAL",
                "SKIPPED",
            ):
                is_ci_passing = False
                break
        prs.append(
            PrRecord(
                number=number,
                head_ref=raw["headRefName"],
                changed_files=tuple(f["path"] for f in files),
                closes_issue_numbers=tuple(
                    sorted(ref["number"] for ref in closing_refs)
                ),
                review_decision=raw.get("reviewDecision") or "",
                is_ci_passing=is_ci_passing,
            )
        )
    return prs


def branch_changed_files(branch: str, base: str = "origin/main") -> list[str]:
    """#232: `base`と共通の祖先を持たない(orphanな)ブランチとの3点diffは
    `fatal: no merge base`でexit 128になる。dispatch-cycle全体をクラッシュ
    させないよう、footprint差分なし（ロック対象外）として扱う。"""
    _validate_ref_name(branch)
    _validate_ref_name(base)
    try:
        stdout = _run(["git", "diff", "--name-only", f"{base}...{branch}"])
    except (subprocess.CalledProcessError, OSError):
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]
