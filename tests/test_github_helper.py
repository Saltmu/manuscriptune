import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.utils.github_helper import (
    create_issue,
    create_issue_cli,
    create_pr,
    create_pr_cli,
)


def test_create_issue_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/Saltmu/novel_tools/issues/100\n",
            stderr="",
        )
        url = create_issue(
            "Test Title", "Test Body", labels=["bug", "high"], assignees=["user1"]
        )
        assert url == "https://github.com/Saltmu/novel_tools/issues/100"

        expected_cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            "Test Title",
            "--body",
            "Test Body",
            "--label",
            "bug",
            "--label",
            "high",
            "--assignee",
            "user1",
        ]
        mock_run.assert_called_once_with(
            expected_cmd, capture_output=True, text=True, check=True
        )


def test_create_issue_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "issue", "create"], stderr="Error: GraphQL error"
        )
        with pytest.raises(subprocess.CalledProcessError):
            create_issue("Title", "Body")


def test_create_pr_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/Saltmu/novel_tools/pull/101\n",
            stderr="",
        )
        url = create_pr("PR Title", "PR Body", base="main", head="feature", draft=True)
        assert url == "https://github.com/Saltmu/novel_tools/pull/101"

        expected_cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            "PR Title",
            "--body",
            "PR Body",
            "--base",
            "main",
            "--head",
            "feature",
            "--draft",
        ]
        mock_run.assert_called_once_with(
            expected_cmd, capture_output=True, text=True, check=True
        )


def test_create_issue_cli():
    with (
        patch("src.utils.github_helper.create_issue") as mock_create,
        patch(
            "sys.argv",
            [
                "create-issue",
                "--title",
                "CLI Title",
                "--body",
                "CLI Body",
                "--label",
                "bug",
                "--assignee",
                "user1",
            ],
        ),
    ):
        mock_create.return_value = "https://github.com/Saltmu/novel_tools/issues/102"
        create_issue_cli()
        mock_create.assert_called_once_with(
            "CLI Title", "CLI Body", labels=["bug"], assignees=["user1"]
        )


def test_create_issue_cli_called_process_error():
    with (
        patch("src.utils.github_helper.create_issue") as mock_create,
        patch(
            "sys.argv", ["create-issue", "--title", "CLI Title", "--body", "CLI Body"]
        ),
    ):
        mock_create.side_effect = subprocess.CalledProcessError(
            returncode=4, cmd=["gh", "issue", "create"], stderr="Mocked CLI Error"
        )
        with pytest.raises(SystemExit) as excinfo:
            create_issue_cli()
        assert excinfo.value.code == 4


def test_create_issue_cli_generic_exception():
    with (
        patch("src.utils.github_helper.create_issue") as mock_create,
        patch(
            "sys.argv", ["create-issue", "--title", "CLI Title", "--body", "CLI Body"]
        ),
    ):
        mock_create.side_effect = Exception("System crash")
        with pytest.raises(SystemExit) as excinfo:
            create_issue_cli()
        assert excinfo.value.code == 1


def test_create_pr_cli():
    with (
        patch("src.utils.github_helper.create_pr") as mock_create,
        patch(
            "sys.argv",
            [
                "create-pr",
                "--title",
                "CLI PR",
                "--body",
                "CLI PR Body",
                "--base",
                "main",
                "--head",
                "feat",
                "--draft",
            ],
        ),
    ):
        mock_create.return_value = "https://github.com/Saltmu/novel_tools/pull/103"
        create_pr_cli()
        mock_create.assert_called_once_with(
            "CLI PR", "CLI PR Body", base="main", head="feat", draft=True
        )


def test_create_pr_cli_called_process_error():
    with (
        patch("src.utils.github_helper.create_pr") as mock_create,
        patch("sys.argv", ["create-pr", "--title", "CLI PR", "--body", "CLI PR Body"]),
    ):
        mock_create.side_effect = subprocess.CalledProcessError(
            returncode=5, cmd=["gh", "pr", "create"], stderr="Mocked PR CLI Error"
        )
        with pytest.raises(SystemExit) as excinfo:
            create_pr_cli()
        assert excinfo.value.code == 5


def test_create_pr_cli_generic_exception():
    with (
        patch("src.utils.github_helper.create_pr") as mock_create,
        patch("sys.argv", ["create-pr", "--title", "CLI PR", "--body", "CLI PR Body"]),
    ):
        mock_create.side_effect = Exception("System crash")
        with pytest.raises(SystemExit) as excinfo:
            create_pr_cli()
        assert excinfo.value.code == 1
