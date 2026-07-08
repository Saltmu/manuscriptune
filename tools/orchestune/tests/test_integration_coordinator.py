from __future__ import annotations

from src.dispatch_targets import (
    ClaudeCodeCloudRoutineDispatchTarget,
    DispatchHandle,
)
from src.integration_coordinator import (
    IntegrationCoordinator,
    build_integration_coordinator,
    build_review_routine_prompt,
)


class _FakeFirer:
    def __init__(self, handle: DispatchHandle):
        self._handle = handle
        self.fired: list[str] = []

    def fire_text(self, text: str) -> DispatchHandle:
        self.fired.append(text)
        return self._handle


class TestBuildReviewRoutinePrompt:
    def test_contains_branches_subtasks_and_parent(self):
        prompt = build_review_routine_prompt(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=181,
            merged_subtask_ids=["task-1", "task-2"],
        )
        assert "integration/temp-main" in prompt
        assert "origin/main" in prompt
        assert "task-1, task-2" in prompt
        assert "#181" in prompt

    def test_instructs_sendback_and_no_auto_merge(self):
        prompt = build_review_routine_prompt(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=181,
            merged_subtask_ids=["task-1"],
        )
        assert "status:done" in prompt
        assert "status:queued" in prompt
        assert "自動マージは絶対に行わない" in prompt

    def test_does_not_carry_prior_findings(self):
        # 再レビュー時のバイアス回避: プロンプトは過去の指摘を含めない設計。
        prompt = build_review_routine_prompt(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=None,
            merged_subtask_ids=["task-1"],
        )
        assert "前回のレビュー内容は与えられていません" in prompt


class TestIntegrationCoordinatorDispatchReview:
    def test_fires_routine_with_prompt_and_returns_handle(self):
        handle = DispatchHandle(
            external_id="sess-1", external_url="https://claude.ai/code/s/sess-1"
        )
        firer = _FakeFirer(handle)
        coord = IntegrationCoordinator(firer)

        result = coord.dispatch_review(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=181,
            merged_subtask_ids=["task-1", "task-2"],
        )

        assert result is handle
        assert len(firer.fired) == 1
        assert "task-1, task-2" in firer.fired[0]
        assert "integration/temp-main" in firer.fired[0]

    def test_each_dispatch_fires_a_fresh_routine_session(self):
        # 差し戻し後の再レビューで新規セッションを使う保証:
        # dispatch_review 呼び出しごとに fire_text が呼ばれる（=新規セッション起動）。
        firer = _FakeFirer(DispatchHandle(external_id="s"))
        coord = IntegrationCoordinator(firer)
        coord.dispatch_review("integration/temp-main", "origin/main", 1, ["task-1"])
        coord.dispatch_review("integration/temp-main", "origin/main", 1, ["task-1"])
        assert len(firer.fired) == 2


class TestBuildIntegrationCoordinator:
    def test_none_without_routine_credentials(self, monkeypatch):
        monkeypatch.delenv("ORCHESTUNE_ROUTINE_ID", raising=False)
        monkeypatch.delenv("ORCHESTUNE_ROUTINE_TOKEN", raising=False)
        assert build_integration_coordinator() is None

    def test_none_when_only_one_credential_present(self, monkeypatch):
        monkeypatch.setenv("ORCHESTUNE_ROUTINE_ID", "rid")
        monkeypatch.delenv("ORCHESTUNE_ROUTINE_TOKEN", raising=False)
        assert build_integration_coordinator() is None

    def test_builds_with_cloud_routine_target_when_credentials_present(
        self, monkeypatch
    ):
        monkeypatch.setenv("ORCHESTUNE_ROUTINE_ID", "rid")
        monkeypatch.setenv("ORCHESTUNE_ROUTINE_TOKEN", "rtok")
        coord = build_integration_coordinator()
        assert isinstance(coord, IntegrationCoordinator)
        assert isinstance(coord._routine_firer, ClaudeCodeCloudRoutineDispatchTarget)
