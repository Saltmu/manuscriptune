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


def _run(args: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def list_issues_by_label(label: str) -> list[IssueRecord]:
    _validate_label(label)
    stdout = _run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            label,
            "--state",
            "open",
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


def list_remote_branches() -> list[str]:
    stdout = _run(["git", "branch", "-r", "--format=%(refname:short)"])
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def list_open_prs() -> list[PrRecord]:
    stdout = _run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName"]
    )
    raw_prs = json.loads(stdout)
    prs: list[PrRecord] = []
    for raw in raw_prs:
        number = raw["number"]
        files_stdout = _run(["gh", "pr", "view", str(number), "--json", "files"])
        files = json.loads(files_stdout).get("files", [])
        prs.append(
            PrRecord(
                number=number,
                head_ref=raw["headRefName"],
                changed_files=tuple(f["path"] for f in files),
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
