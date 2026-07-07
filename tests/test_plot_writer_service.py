from unittest.mock import patch

import pytest

from src.services import plot_writer_service
from src.services.plot_writer_service import PlotWriterServiceError
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

    with patch(
        "src.services.plot_writer_service.PlotExpansionTask.execute",
        return_value="肉付けされたプロット",
    ) as mock_execute:
        result = plot_writer_service.expand_plot(
            plot_file=str(plot_file), focus_instructions="もっと葛藤を"
        )

    assert result == "肉付けされたプロット"
    assert mock_execute.called
    called_input = mock_execute.call_args[0][0]
    assert called_input.plot_content == "第1章：テスト章"
    assert called_input.focus_instructions == "もっと葛藤を"


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
