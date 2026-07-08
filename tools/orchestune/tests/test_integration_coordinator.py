from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from src.integration_coordinator import (
    IntegrationCoordinator,
    SemanticFinding,
    SubprocessReviewer,
    _extract_json_object,
    build_integration_coordinator,
    build_review_prompt,
)


class TestExtractJsonObject:
    def test_plain_json(self):
        assert _extract_json_object('{"passed": true}') == {"passed": True}

    def test_json_in_markdown_fence(self):
        text = (
            'ここが結論です:\n```json\n{"passed": false, "findings": []}\n```\n以上。'
        )
        assert _extract_json_object(text) == {"passed": False, "findings": []}

    def test_json_with_braces_in_string(self):
        text = '{"reason": "config{a} と config{b} が競合"}'
        assert _extract_json_object(text) == {"reason": "config{a} と config{b} が競合"}

    def test_no_json_returns_none(self):
        assert _extract_json_object("JSONはありません") is None

    def test_invalid_json_returns_none(self):
        assert _extract_json_object("{not valid json,,,}") is None

    def test_non_object_returns_none(self):
        assert _extract_json_object("[1, 2, 3]") is None


class TestBuildReviewPrompt:
    def test_contains_diff_and_subtasks(self):
        prompt = build_review_prompt("diff --git a/x b/x", ["task-1", "task-2"])
        assert "diff --git a/x b/x" in prompt
        assert "task-1, task-2" in prompt

    def test_does_not_carry_prior_findings(self):
        # 再レビュー時のバイアス回避: プロンプト構築は過去の指摘を受け取らない設計。
        prompt = build_review_prompt("some diff", ["task-1"])
        assert "前回" not in prompt
        assert "以前の指摘" not in prompt


class TestIntegrationCoordinatorReview:
    def _coordinator(self, reviewer, factory_calls=None):
        def factory():
            if factory_calls is not None:
                factory_calls.append(1)
            return reviewer

        return IntegrationCoordinator(reviewer_factory=factory)

    @patch("src.integration_coordinator.subprocess.run")
    def test_review_passed(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n+code"
        )

        def reviewer(prompt):
            return '{"passed": true, "findings": []}'

        coord = self._coordinator(reviewer)
        result = coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert result.passed is True
        assert result.findings == ()

    @patch("src.integration_coordinator.subprocess.run")
    def test_review_failed_with_findings(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n+code"
        )
        response = json.dumps(
            {
                "passed": False,
                "findings": [
                    {"subtask_id": "task-2", "reason": "共有設定への競合更新"}
                ],
            }
        )
        coord = self._coordinator(lambda prompt: response)
        result = coord.review(Path("."), "origin/main", "temp", ["task-1", "task-2"])
        assert result.passed is False
        assert result.findings == (
            SemanticFinding(subtask_id="task-2", reason="共有設定への競合更新"),
        )

    @patch("src.integration_coordinator.subprocess.run")
    def test_unparseable_response_failsafe_passes(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n+code"
        )
        coord = self._coordinator(lambda prompt: "JSONを含まない応答")
        result = coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert result.passed is True

    @patch("src.integration_coordinator.subprocess.run")
    def test_reviewer_exception_failsafe_passes(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n+code"
        )

        def raising_reviewer(prompt):
            raise RuntimeError("CLI not found")

        coord = self._coordinator(raising_reviewer)
        result = coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert result.passed is True
        assert "reviewer error" in result.raw

    @patch("src.integration_coordinator.subprocess.run")
    def test_empty_diff_failsafe_passes_without_calling_reviewer(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="   \n"
        )
        called = []

        def reviewer(prompt):
            called.append(prompt)
            return '{"passed": false}'

        coord = self._coordinator(reviewer)
        result = coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert result.passed is True
        assert called == []  # diffが空ならReviewerは起動しない

    @patch("src.integration_coordinator.subprocess.run")
    def test_diff_collection_failure_failsafe_passes(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["git", "diff"]
        )
        coord = self._coordinator(lambda prompt: '{"passed": false}')
        result = coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert result.passed is True

    @patch("src.integration_coordinator.subprocess.run")
    def test_fresh_instance_created_per_review(self, mock_run):
        # 差し戻し後の再レビューで新規インスタンスを使う保証:
        # review()呼び出しごとにreviewer_factory()が呼ばれる。
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n+code"
        )
        factory_calls: list[int] = []
        coord = self._coordinator(
            lambda prompt: '{"passed": true}', factory_calls=factory_calls
        )
        coord.review(Path("."), "origin/main", "temp", ["task-1"])
        coord.review(Path("."), "origin/main", "temp", ["task-1"])
        assert len(factory_calls) == 2


class TestSubprocessReviewer:
    @patch("src.integration_coordinator.subprocess.run")
    def test_unwraps_claude_code_json_envelope(self, mock_run):
        envelope = json.dumps({"type": "result", "result": '{"passed": true}'})
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=envelope
        )
        reviewer = SubprocessReviewer()
        assert reviewer("prompt") == '{"passed": true}'

    @patch("src.integration_coordinator.subprocess.run")
    def test_returns_raw_when_not_enveloped(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="plain text answer"
        )
        reviewer = SubprocessReviewer()
        assert reviewer("prompt") == "plain text answer"

    @patch("src.integration_coordinator.subprocess.run")
    def test_passes_prompt_as_single_arg_not_shell(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}"
        )
        reviewer = SubprocessReviewer(command_prefix=["claude", "-p"])
        reviewer("rm -rf / ; echo pwned")
        called_args = mock_run.call_args.args[0]
        # プロンプトは単一の引数として渡り、シェル解釈されない
        assert called_args[0] == "claude"
        assert "rm -rf / ; echo pwned" in called_args
        assert "--output-format" in called_args

    @patch("src.integration_coordinator.time.sleep")
    @patch("src.integration_coordinator.subprocess.run")
    def test_retries_with_backoff_then_succeeds(self, mock_run, mock_sleep):
        mock_run.side_effect = [
            subprocess.CalledProcessError(returncode=1, cmd=["claude"]),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="{}"),
        ]
        reviewer = SubprocessReviewer(max_retries=3, initial_delay=1.0)
        assert reviewer("prompt") == "{}"
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("src.integration_coordinator.time.sleep")
    @patch("src.integration_coordinator.subprocess.run")
    def test_raises_after_exhausting_retries(self, mock_run, mock_sleep):
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["claude"]
        )
        reviewer = SubprocessReviewer(max_retries=2, initial_delay=1.0)
        try:
            reviewer("prompt")
            raise AssertionError("should have raised")
        except subprocess.CalledProcessError:
            pass
        assert mock_run.call_count == 3  # 初回 + 2リトライ
        # バックオフは 1.0, 2.0 の2回
        assert mock_sleep.call_count == 2


class TestBuildIntegrationCoordinator:
    def test_builds_with_subprocess_reviewer(self):
        coord = build_integration_coordinator()
        assert isinstance(coord, IntegrationCoordinator)
        reviewer = coord._reviewer_factory()
        assert isinstance(reviewer, SubprocessReviewer)
