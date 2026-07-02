import argparse
import subprocess
import sys


def create_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> str:
    """Create a GitHub issue using the gh CLI safely."""
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    if labels:
        for label in labels:
            cmd.extend(["--label", label])
    if assignees:
        for assignee in assignees:
            cmd.extend(["--assignee", assignee])

    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def create_pr(
    title: str,
    body: str,
    base: str | None = None,
    head: str | None = None,
    draft: bool = False,
) -> str:
    """Create a GitHub pull request using the gh CLI safely."""
    cmd = ["gh", "pr", "create", "--title", title, "--body", body]
    if base:
        cmd.extend(["--base", base])
    if head:
        cmd.extend(["--head", head])
    if draft:
        cmd.append("--draft")

    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def create_issue_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Create a GitHub Issue safely using gh CLI"
    )
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--body", required=True, help="Issue body content")
    parser.add_argument("--label", action="append", help="Labels to apply to the issue")
    parser.add_argument("--assignee", action="append", help="Assignees for the issue")
    args = parser.parse_args()

    try:
        url = create_issue(
            args.title, args.body, labels=args.label, assignees=args.assignee
        )
        print(f"Issue created successfully: {url}")
    except subprocess.CalledProcessError as e:
        print(
            f"Failed to create issue. Status: {e.returncode}. Error: {e.stderr}",
            file=sys.stderr,
        )
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def create_pr_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Create a GitHub PR safely using gh CLI"
    )
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--body", required=True, help="PR body content")
    parser.add_argument(
        "--base", help="The branch into which you want your code merged"
    )
    parser.add_argument("--head", help="The branch that contains your commits")
    parser.add_argument("--draft", action="store_true", help="Create the PR as a draft")
    args = parser.parse_args()

    try:
        url = create_pr(
            args.title, args.body, base=args.base, head=args.head, draft=args.draft
        )
        print(f"PR created successfully: {url}")
    except subprocess.CalledProcessError as e:
        print(
            f"Failed to create PR. Status: {e.returncode}. Error: {e.stderr}",
            file=sys.stderr,
        )
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
