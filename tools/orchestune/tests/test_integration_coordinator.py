from __future__ import annotations

from unittest.mock import patch

from src.dispatch_targets import (
    ClaudeCodeCloudRoutineDispatchTarget,
    DispatchHandle,
)
from src.integration_coordinator import (
    FAILED_LABEL,
    PASSED_LABEL,
    IntegrationCoordinator,
    build_integration_coordinator,
    build_review_routine_prompt,
    process_pending_reviews,
    record_pending_review,
)
from src.integration_review_state import (
    IntegrationReviewState,
    PendingSemanticReview,
    PendingSubtaskMerge,
    load_integration_review_state,
    save_integration_review_state,
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

    def test_instructs_sendback_and_forbids_merge(self):
        prompt = build_review_routine_prompt(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=181,
            merged_subtask_ids=["task-1"],
        )
        assert "status:done" in prompt
        assert "status:queued" in prompt
        assert "gh pr merge" in prompt
        assert "絶対に実行しないでください" in prompt

    def test_instructs_label_based_signaling(self):
        prompt = build_review_routine_prompt(
            temp_branch="integration/temp-main",
            base_branch="origin/main",
            parent_issue_number=181,
            merged_subtask_ids=["task-1"],
        )
        assert PASSED_LABEL in prompt
        assert FAILED_LABEL in prompt

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


class TestRecordPendingReview:
    def test_appends_pending_entry_with_session_handle(self, tmp_path):
        path = tmp_path / "state.json"
        handle = DispatchHandle(
            external_id="sess-1", external_url="https://claude.ai/code/s/sess-1"
        )
        record_pending_review(
            path,
            parent_issue_number=181,
            subtask_prs=[("task-1", 10, 20), ("task-2", 11, 21)],
            session_handle=handle,
        )

        state = load_integration_review_state(path)
        assert len(state.pending) == 1
        entry = state.pending[0]
        assert entry.parent_issue_number == 181
        assert entry.session_external_id == "sess-1"
        assert entry.subtask_prs == (
            PendingSubtaskMerge(subtask_id="task-1", issue_number=10, pr_number=20),
            PendingSubtaskMerge(subtask_id="task-2", issue_number=11, pr_number=21),
        )

    def test_appends_without_clobbering_existing_pending_entries(self, tmp_path):
        path = tmp_path / "state.json"
        record_pending_review(
            path, 1, [("task-1", 10, 20)], DispatchHandle(external_id="a")
        )
        record_pending_review(
            path, 2, [("task-2", 11, 21)], DispatchHandle(external_id="b")
        )
        state = load_integration_review_state(path)
        assert len(state.pending) == 2


class TestProcessPendingReviews:
    def _state_with(self, *entries: PendingSemanticReview, path):
        save_integration_review_state(
            IntegrationReviewState(pending=list(entries)), path
        )

    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_no_pending_reviews_is_a_noop(self, mock_labels, tmp_path):
        path = tmp_path / "state.json"
        result = process_pending_reviews(path)
        assert result == {"merged": [], "failed": [], "still_pending": 0}
        mock_labels.assert_not_called()

    @patch("src.integration_coordinator.github.add_comment")
    @patch("src.integration_coordinator.github.remove_label")
    @patch("src.integration_coordinator.github.merge_pr")
    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_passed_label_merges_prs_in_order_and_clears_label(
        self, mock_labels, mock_merge, mock_remove, mock_comment, tmp_path
    ):
        path = tmp_path / "state.json"
        self._state_with(
            PendingSemanticReview(
                parent_issue_number=181,
                dispatched_at=1.0,
                subtask_prs=(
                    PendingSubtaskMerge(
                        subtask_id="task-1", issue_number=10, pr_number=20
                    ),
                    PendingSubtaskMerge(
                        subtask_id="task-2", issue_number=11, pr_number=21
                    ),
                ),
            ),
            path=path,
        )
        mock_labels.return_value = (PASSED_LABEL,)

        result = process_pending_reviews(path)

        assert mock_merge.call_args_list[0].args == (20,)
        assert mock_merge.call_args_list[1].args == (21,)
        mock_remove.assert_called_once_with(181, PASSED_LABEL)
        assert result["merged"] == [
            {"parent_issue_number": 181, "merged_subtasks": ["task-1", "task-2"]}
        ]
        assert result["still_pending"] == 0
        # 消費済みレコードは状態ファイルから削除される
        assert load_integration_review_state(path).pending == []

    @patch("src.integration_coordinator.github.add_comment")
    @patch("src.integration_coordinator.github.remove_label")
    @patch("src.integration_coordinator.github.merge_pr")
    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_one_pr_merge_failure_does_not_block_the_others(
        self, mock_labels, mock_merge, mock_remove, mock_comment, tmp_path
    ):
        path = tmp_path / "state.json"
        self._state_with(
            PendingSemanticReview(
                parent_issue_number=181,
                dispatched_at=1.0,
                subtask_prs=(
                    PendingSubtaskMerge(
                        subtask_id="task-1", issue_number=10, pr_number=20
                    ),
                    PendingSubtaskMerge(
                        subtask_id="task-2", issue_number=11, pr_number=21
                    ),
                ),
            ),
            path=path,
        )
        mock_labels.return_value = (PASSED_LABEL,)

        def merge_side_effect(pr_number, *args, **kwargs):
            if pr_number == 20:
                raise RuntimeError("already merged")

        mock_merge.side_effect = merge_side_effect

        result = process_pending_reviews(path)

        assert mock_merge.call_count == 2
        assert result["merged"] == [
            {"parent_issue_number": 181, "merged_subtasks": ["task-2"]}
        ]

    @patch("src.integration_coordinator.github.add_comment")
    @patch("src.integration_coordinator.github.remove_label")
    @patch("src.integration_coordinator.github.merge_pr")
    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_failed_label_clears_without_merging(
        self, mock_labels, mock_merge, mock_remove, mock_comment, tmp_path
    ):
        path = tmp_path / "state.json"
        self._state_with(
            PendingSemanticReview(
                parent_issue_number=181,
                dispatched_at=1.0,
                subtask_prs=(
                    PendingSubtaskMerge(
                        subtask_id="task-1", issue_number=10, pr_number=20
                    ),
                ),
            ),
            path=path,
        )
        mock_labels.return_value = (FAILED_LABEL,)

        result = process_pending_reviews(path)

        mock_merge.assert_not_called()
        mock_remove.assert_called_once_with(181, FAILED_LABEL)
        assert result["failed"] == [181]
        assert load_integration_review_state(path).pending == []

    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_neither_label_present_keeps_entry_pending(self, mock_labels, tmp_path):
        path = tmp_path / "state.json"
        entry = PendingSemanticReview(
            parent_issue_number=181,
            dispatched_at=1.0,
            subtask_prs=(
                PendingSubtaskMerge(subtask_id="task-1", issue_number=10, pr_number=20),
            ),
        )
        self._state_with(entry, path=path)
        mock_labels.return_value = ("status:done",)

        result = process_pending_reviews(path)

        assert result["still_pending"] == 1
        assert load_integration_review_state(path).pending == [entry]

    @patch("src.integration_coordinator.github.get_issue_labels")
    def test_label_polling_failure_keeps_entry_pending(self, mock_labels, tmp_path):
        path = tmp_path / "state.json"
        entry = PendingSemanticReview(
            parent_issue_number=181,
            dispatched_at=1.0,
            subtask_prs=(
                PendingSubtaskMerge(subtask_id="task-1", issue_number=10, pr_number=20),
            ),
        )
        self._state_with(entry, path=path)
        mock_labels.side_effect = RuntimeError("gh api error")

        result = process_pending_reviews(path)

        assert result["still_pending"] == 1
        assert load_integration_review_state(path).pending == [entry]


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
