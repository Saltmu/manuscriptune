import subprocess
from unittest.mock import patch

import pytest

from src.github import (
    IssueRecord,
    PrRecord,
    _validate_issue_number,
    _validate_label,
    _validate_ref_name,
    add_comment,
    add_label,
    branch_changed_files,
    list_issues_by_label,
    list_open_prs,
    list_remote_branches,
    remove_label,
)


class TestValidateIssueNumber:
    def test_accepts_positive_int(self):
        assert _validate_issue_number(184) == 184

    def test_accepts_numeric_string(self):
        assert _validate_issue_number("184") == 184

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="issue番号"):
            _validate_issue_number("184; rm -rf /")

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="issue番号"):
            _validate_issue_number(-1)

    def test_rejects_zero(self):
        with pytest.raises(ValueError, match="issue番号"):
            _validate_issue_number(0)


class TestValidateLabel:
    def test_accepts_known_label_pattern(self):
        assert _validate_label("status:queued") == "status:queued"
        assert _validate_label("priority:high") == "priority:high"
        assert _validate_label("risk:flagged") == "risk:flagged"

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(ValueError, match="ラベル"):
            _validate_label("status:queued; rm -rf /")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="ラベル"):
            _validate_label("status queued")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="ラベル"):
            _validate_label("")


class TestValidateRefName:
    def test_accepts_normal_branch_name(self):
        assert _validate_ref_name("claude/issue-184-dispatcher") == (
            "claude/issue-184-dispatcher"
        )

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(ValueError, match="ブランチ名"):
            _validate_ref_name("foo`rm -rf /`")

    def test_rejects_leading_dash(self):
        with pytest.raises(ValueError, match="ブランチ名"):
            _validate_ref_name("--force")

    def test_rejects_double_dot(self):
        with pytest.raises(ValueError, match="ブランチ名"):
            _validate_ref_name("foo..bar")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="ブランチ名"):
            _validate_ref_name("")


class TestListIssuesByLabel:
    def test_calls_gh_with_list_args_and_parses_json(self):
        payload = (
            '[{"number": 1, "title": "t", "body": "b", '
            '"labels": [{"name": "status:queued"}], "createdAt": "2026-01-01T00:00:00Z"}]'
        )
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=payload, stderr=""
            )
            result = list_issues_by_label("status:queued")

        called_args = mock_run.call_args.args[0]
        assert called_args[0] == "gh"
        assert "--label" in called_args
        assert "status:queued" in called_args
        assert mock_run.call_args.kwargs.get("shell", False) is False
        assert result == [
            IssueRecord(
                number=1,
                title="t",
                body="b",
                labels=("status:queued",),
                created_at="2026-01-01T00:00:00Z",
            )
        ]

    def test_rejects_invalid_label_before_calling_subprocess(self):
        with patch("src.github.subprocess.run") as mock_run:
            with pytest.raises(ValueError):
                list_issues_by_label("status:queued; evil")
            mock_run.assert_not_called()


class TestAddRemoveLabel:
    def test_add_label_calls_gh_issue_edit(self):
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            add_label(184, "status:in-progress")
        called_args = mock_run.call_args.args[0]
        assert called_args == [
            "gh",
            "issue",
            "edit",
            "184",
            "--add-label",
            "status:in-progress",
        ]

    def test_remove_label_calls_gh_issue_edit(self):
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            remove_label(184, "status:queued")
        called_args = mock_run.call_args.args[0]
        assert called_args == [
            "gh",
            "issue",
            "edit",
            "184",
            "--remove-label",
            "status:queued",
        ]

    def test_add_label_rejects_invalid_issue_number(self):
        with patch("src.github.subprocess.run") as mock_run:
            with pytest.raises(ValueError):
                add_label("184 && evil", "status:queued")
            mock_run.assert_not_called()


class TestAddComment:
    def test_passes_body_via_stdin_not_argv(self):
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            add_comment(184, "some body with `backticks` and $(dangerous)")
        called_args = mock_run.call_args.args[0]
        assert called_args == ["gh", "issue", "comment", "184", "--body-file", "-"]
        assert (
            mock_run.call_args.kwargs.get("input")
            == "some body with `backticks` and $(dangerous)"
        )


class TestListRemoteBranches:
    def test_parses_branch_lines(self):
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="origin/main\norigin/feat/foo\n",
                stderr="",
            )
            branches = list_remote_branches()
        assert branches == ["origin/main", "origin/feat/foo"]


class TestListOpenPrs:
    def test_fetches_pr_list_and_per_pr_files(self):
        list_payload = '[{"number": 5, "headRefName": "feat/x"}]'
        files_payload = '{"files": [{"path": "src/a.py"}, {"path": "src/b.py"}]}'

        with patch("src.github.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=list_payload, stderr=""
                ),
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=files_payload, stderr=""
                ),
            ]
            prs = list_open_prs()

        assert prs == [
            PrRecord(
                number=5, head_ref="feat/x", changed_files=("src/a.py", "src/b.py")
            )
        ]


class TestBranchChangedFiles:
    def test_calls_git_diff_name_only(self):
        with patch("src.github.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="src/a.py\nsrc/b.py\n", stderr=""
            )
            files = branch_changed_files("origin/feat/x")
        called_args = mock_run.call_args.args[0]
        assert called_args[:2] == ["git", "diff"]
        assert "origin/main...origin/feat/x" in called_args
        assert files == ["src/a.py", "src/b.py"]

    def test_rejects_invalid_branch_name(self):
        with patch("src.github.subprocess.run") as mock_run:
            with pytest.raises(ValueError):
                branch_changed_files("--upload-pack=evil")
            mock_run.assert_not_called()
