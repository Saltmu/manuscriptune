import os
from unittest.mock import patch

import pytest

from src.services import plot_writer_service
from src.services.plot_writer_service import PlotWriterServiceError
from src.utils import project_paths
from src.utils.cancellation import CancellationToken, PipelineCancelledError


def test_expand_plot_raises_when_plot_file_missing(tmp_path):
    missing_plot = tmp_path / "does_not_exist.txt"
    with pytest.raises(PlotWriterServiceError):
        plot_writer_service.expand_plot(plot_file=str(missing_plot))


def test_expand_plot_checks_cancellation_before_generating(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")

    token = CancellationToken()
    token.cancel()

    with pytest.raises(PipelineCancelledError):
        plot_writer_service.expand_plot(plot_file=str(plot_file), cancel_token=token)


def test_expand_plot_success(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")
    output_dir = tmp_path / "output"

    with (
        patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)),
        patch(
            "src.services.plot_writer_service.PlotExpansionTask.execute",
            return_value="肉付けされたプロット",
        ) as mock_execute,
    ):
        result = plot_writer_service.expand_plot(
            plot_file=str(plot_file), focus_instructions="もっと葛藤を"
        )

    assert result == "肉付けされたプロット"
    assert mock_execute.called
    called_input = mock_execute.call_args[0][0]
    assert called_input.plot_content == "第1章：テスト章"
    assert called_input.focus_instructions == "もっと葛藤を"


def test_expand_plot_saves_draft_to_output_dir(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")
    output_dir = tmp_path / "output"

    with (
        patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)),
        patch(
            "src.services.plot_writer_service.PlotExpansionTask.execute",
            return_value="肉付けされたプロット",
        ),
    ):
        plot_writer_service.expand_plot(plot_file=str(plot_file))

    draft_path = project_paths.get_plot_draft_path(str(output_dir), "plot")
    assert os.path.exists(draft_path)
    with open(draft_path, encoding="utf-8") as f:
        assert f.read() == "肉付けされたプロット\n"


def test_expand_plot_archives_previous_draft_before_overwriting(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")
    output_dir = tmp_path / "output"
    os.makedirs(output_dir)
    draft_path = project_paths.get_plot_draft_path(str(output_dir), "plot")
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write("旧ドラフト\n")

    with (
        patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)),
        patch(
            "src.services.plot_writer_service.PlotExpansionTask.execute",
            return_value="新しいドラフト",
        ),
    ):
        plot_writer_service.expand_plot(plot_file=str(plot_file))

    with open(draft_path, encoding="utf-8") as f:
        assert f.read() == "新しいドラフト\n"

    archived_path = os.path.join(output_dir, "history", "v1", "plot_plot_draft.txt")
    assert os.path.exists(archived_path)
    with open(archived_path, encoding="utf-8") as f:
        assert f.read() == "旧ドラフト\n"


def test_expand_plot_rejects_saving_under_data_sources(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")
    unsafe_output_dir = tmp_path / "data" / "sources" / "plot"

    with (
        patch(
            "src.utils.project_paths.get_output_dir",
            return_value=str(unsafe_output_dir),
        ),
        patch(
            "src.services.plot_writer_service.PlotExpansionTask.execute",
            return_value="肉付けされたプロット",
        ),
    ):
        with pytest.raises(PlotWriterServiceError):
            plot_writer_service.expand_plot(plot_file=str(plot_file))

    assert not os.path.exists(unsafe_output_dir)


def test_revise_plot_with_findings_raises_when_plot_file_missing(tmp_path):
    missing_plot = tmp_path / "does_not_exist.txt"
    with pytest.raises(PlotWriterServiceError):
        plot_writer_service.revise_plot_with_findings(plot_file=str(missing_plot))


def test_revise_plot_with_findings_raises_when_findings_missing(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")

    with patch("src.utils.project_paths.get_output_dir", return_value=str(tmp_path)):
        with pytest.raises(PlotWriterServiceError):
            plot_writer_service.revise_plot_with_findings(plot_file=str(plot_file))


def test_revise_plot_with_findings_success(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("第1章：テスト章", encoding="utf-8")
    findings_yaml = tmp_path / "plot_plot_findings.yaml"
    findings_yaml.write_text("findings: []", encoding="utf-8")

    with (
        patch("src.utils.project_paths.get_output_dir", return_value=str(tmp_path)),
        patch(
            "src.services.plot_writer_service.PlotRevisionTask.execute",
            return_value="改稿されたプロット",
        ) as mock_execute,
    ):
        result = plot_writer_service.revise_plot_with_findings(plot_file=str(plot_file))

    assert result == "改稿されたプロット"
    called_input = mock_execute.call_args[0][0]
    assert called_input.plot_content == "第1章：テスト章"
    assert called_input.findings_yaml == "findings: []"

    draft_path = project_paths.get_plot_draft_path(str(tmp_path), "plot")
    assert os.path.exists(draft_path)
    with open(draft_path, encoding="utf-8") as f:
        assert f.read() == "改稿されたプロット\n"
