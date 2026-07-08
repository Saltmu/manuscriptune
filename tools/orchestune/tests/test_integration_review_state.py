from __future__ import annotations

from src.integration_review_state import (
    IntegrationReviewState,
    PendingSemanticReview,
    PendingSubtaskMerge,
    load_integration_review_state,
    save_integration_review_state,
)


class TestIntegrationReviewStateRoundTrip:
    def test_load_missing_file_returns_empty_state(self, tmp_path):
        state = load_integration_review_state(tmp_path / "does-not-exist.json")
        assert state.pending == []

    def test_save_then_load_round_trips(self, tmp_path):
        path = tmp_path / "integration_review_state.json"
        state = IntegrationReviewState(
            pending=[
                PendingSemanticReview(
                    parent_issue_number=181,
                    dispatched_at=1234.5,
                    subtask_prs=(
                        PendingSubtaskMerge(
                            subtask_id="task-1", issue_number=10, pr_number=20
                        ),
                        PendingSubtaskMerge(
                            subtask_id="task-2", issue_number=11, pr_number=21
                        ),
                    ),
                    session_external_id="sess-1",
                    session_external_url="https://claude.ai/code/s/sess-1",
                )
            ]
        )

        save_integration_review_state(state, path)
        loaded = load_integration_review_state(path)

        assert len(loaded.pending) == 1
        entry = loaded.pending[0]
        assert entry.parent_issue_number == 181
        assert entry.dispatched_at == 1234.5
        assert entry.subtask_prs == (
            PendingSubtaskMerge(subtask_id="task-1", issue_number=10, pr_number=20),
            PendingSubtaskMerge(subtask_id="task-2", issue_number=11, pr_number=21),
        )
        assert entry.session_external_id == "sess-1"
        assert entry.session_external_url == "https://claude.ai/code/s/sess-1"

    def test_save_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "state.json"
        save_integration_review_state(IntegrationReviewState(), path)
        assert path.exists()

    def test_optional_session_fields_default_none_on_load(self, tmp_path):
        path = tmp_path / "state.json"
        state = IntegrationReviewState(
            pending=[
                PendingSemanticReview(
                    parent_issue_number=1,
                    dispatched_at=1.0,
                    subtask_prs=(),
                )
            ]
        )
        save_integration_review_state(state, path)
        loaded = load_integration_review_state(path)
        assert loaded.pending[0].session_external_id is None
        assert loaded.pending[0].session_external_url is None
