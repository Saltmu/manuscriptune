from __future__ import annotations

import json
import subprocess
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from src.integration_coordinator import (
    AnthropicApiReviewer,
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


def _http_response(payload: dict):
    return BytesIO(json.dumps(payload).encode("utf-8"))


class TestAnthropicApiReviewer:
    @patch("src.integration_coordinator.urllib.request.urlopen")
    def test_extracts_text_from_content_blocks(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = _http_response(
            {
                "content": [
                    {"type": "thinking", "text": ""},
                    {"type": "text", "text": '{"passed": '},
                    {"type": "text", "text": "true}"},
                ]
            }
        )
        reviewer = AnthropicApiReviewer(api_key="sk-test")
        assert reviewer("prompt") == '{"passed": true}'

    @patch("src.integration_coordinator.urllib.request.urlopen")
    def test_sends_opus_model_and_no_sampling_params(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = _http_response(
            {"content": [{"type": "text", "text": "{}"}]}
        )
        reviewer = AnthropicApiReviewer(api_key="sk-test")
        reviewer("prompt")
        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        assert body["model"] == "claude-opus-4-8"
        assert body["output_config"] == {"effort": "high"}
        # Opus 4.8 は temperature 等を受け付けない（送ると400）ため含めない
        assert "temperature" not in body
        assert "top_p" not in body
        assert "thinking" not in body
        # 認証・バージョンヘッダが付与される
        assert request.headers["X-api-key"] == "sk-test"
        assert request.headers["Anthropic-version"] == "2023-06-01"

    @patch("src.integration_coordinator.time.sleep")
    @patch("src.integration_coordinator.urllib.request.urlopen")
    def test_retries_on_429_then_succeeds(self, mock_urlopen, mock_sleep):
        err = urllib.error.HTTPError(
            url="x", code=429, msg="rate limited", hdrs=None, fp=None
        )
        ok = type(
            "Ctx",
            (),
            {
                "__enter__": lambda s: _http_response(
                    {"content": [{"type": "text", "text": "{}"}]}
                ),
                "__exit__": lambda *a: False,
            },
        )()
        mock_urlopen.side_effect = [err, ok]
        reviewer = AnthropicApiReviewer(api_key="sk-test", max_retries=3)
        assert reviewer("prompt") == "{}"
        assert mock_urlopen.call_count == 2

    @patch("src.integration_coordinator.time.sleep")
    @patch("src.integration_coordinator.urllib.request.urlopen")
    def test_4xx_not_retried(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="x", code=401, msg="unauthorized", hdrs=None, fp=None
        )
        reviewer = AnthropicApiReviewer(api_key="bad", max_retries=3)
        try:
            reviewer("prompt")
            raise AssertionError("should have raised")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        assert mock_urlopen.call_count == 1  # 4xxは即時送出、リトライしない


class TestBuildIntegrationCoordinator:
    def test_uses_api_reviewer_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        coord = build_integration_coordinator()
        assert isinstance(coord, IntegrationCoordinator)
        assert isinstance(coord._reviewer_factory(), AnthropicApiReviewer)

    def test_falls_back_to_subprocess_reviewer_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        coord = build_integration_coordinator()
        assert isinstance(coord._reviewer_factory(), SubprocessReviewer)
