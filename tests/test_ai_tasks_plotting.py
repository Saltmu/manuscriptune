from unittest.mock import MagicMock, patch

from src.utils.ai_task import (
    PlotExpansionInput,
    PlotExpansionTask,
    PlotRevisionInput,
    PlotRevisionTask,
)


@patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
def test_plot_expansion_task_render_prompt_passthrough(mock_resolve, mock_read):
    task = PlotExpansionTask()
    input_data = PlotExpansionInput(
        plot_content="第1章：テスト章\nシーン1：テストシーン",
        focus_instructions="もっと葛藤を強めてほしい",
    )

    prompt = task.render_prompt(input_data)
    assert "第1章：テスト章" in prompt
    assert "シーン1：テストシーン" in prompt
    assert "もっと葛藤を強めてほしい" in prompt


@patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
def test_plot_expansion_task_render_prompt_includes_gmco_and_structure_guidance(
    mock_resolve, mock_read
):
    task = PlotExpansionTask()
    input_data = PlotExpansionInput(plot_content="元のプロット")

    prompt = task.render_prompt(input_data)
    assert "GMCO" in prompt
    assert "三幕構成" in prompt
    assert "第N章：" in prompt
    assert "第N話：" in prompt
    assert "シーンN：" in prompt


@patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
def test_plot_expansion_task_render_prompt_without_focus_instructions(
    mock_resolve, mock_read
):
    task = PlotExpansionTask()
    input_data = PlotExpansionInput(plot_content="元のプロット")

    prompt = task.render_prompt(input_data)
    assert "重点指示" not in prompt


def test_plot_expansion_task_execute_calls_client_with_callback():
    task = PlotExpansionTask()
    task.client = MagicMock()
    task.client.generate.return_value = "肉付けされたプロット"
    input_data = PlotExpansionInput(plot_content="元のプロット")

    callback = MagicMock()
    with (
        patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy"),
        patch(
            "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
    ):
        result = task.execute(input_data, callback=callback)

    assert result == "肉付けされたプロット"
    task.client.generate.assert_called_once()
    _args, kwargs = task.client.generate.call_args
    assert kwargs["callback"] is callback


def test_plot_expansion_task_postprocess_strips_code_fence():
    task = PlotExpansionTask()
    input_data = PlotExpansionInput(plot_content="元のプロット")

    raw_output = "```\n第1章：テスト章\nシーン1：詳細化されたシーン\n```"
    processed = task.postprocess(raw_output, input_data)
    assert processed == "第1章：テスト章\nシーン1：詳細化されたシーン"


@patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
def test_plot_revision_task_render_prompt_passthrough(mock_resolve, mock_read):
    task = PlotRevisionTask()
    input_data = PlotRevisionInput(
        plot_content="第1章：テスト章",
        findings_yaml="findings: []",
    )

    prompt = task.render_prompt(input_data)
    assert "第1章：テスト章" in prompt
    assert "findings: []" in prompt
    assert "第N章：" in prompt
    assert "シーンN：" in prompt


def test_plot_revision_task_execute_calls_client_with_callback():
    task = PlotRevisionTask()
    task.client = MagicMock()
    task.client.generate.return_value = "改稿されたプロット"
    input_data = PlotRevisionInput(
        plot_content="元のプロット", findings_yaml="findings: []"
    )

    callback = MagicMock()
    with (
        patch("src.utils.ai_tasks.plotting.read_file", return_value="dummy"),
        patch(
            "src.utils.ai_tasks.plotting.writer_helper.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
    ):
        result = task.execute(input_data, callback=callback)

    assert result == "改稿されたプロット"
    task.client.generate.assert_called_once()
    _args, kwargs = task.client.generate.call_args
    assert kwargs["callback"] is callback


def test_plot_revision_task_postprocess_strips_code_fence():
    task = PlotRevisionTask()
    input_data = PlotRevisionInput(
        plot_content="元のプロット", findings_yaml="findings: []"
    )

    raw_output = "```markdown\n第1章：テスト章\nシーン1：改稿されたシーン\n```"
    processed = task.postprocess(raw_output, input_data)
    assert processed == "第1章：テスト章\nシーン1：改稿されたシーン"
