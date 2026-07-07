from unittest.mock import MagicMock

from src.utils.ai_task import (
    PlotExpansionInput,
    PlotExpansionTask,
    PlotRevisionInput,
    PlotRevisionTask,
)


def test_plot_expansion_task_render_prompt_passthrough():
    task = PlotExpansionTask()
    input_data = PlotExpansionInput(
        plot_content="第1章：テスト章\nシーン1：テストシーン",
        focus_instructions="もっと葛藤を強めてほしい",
    )

    prompt = task.render_prompt(input_data)
    assert "第1章：テスト章" in prompt


def test_plot_expansion_task_execute_calls_client_with_callback():
    task = PlotExpansionTask()
    task.client = MagicMock()
    task.client.generate.return_value = "肉付けされたプロット"
    input_data = PlotExpansionInput(plot_content="元のプロット")

    callback = MagicMock()
    result = task.execute(input_data, callback=callback)

    assert result == "肉付けされたプロット"
    task.client.generate.assert_called_once()
    _args, kwargs = task.client.generate.call_args
    assert kwargs["callback"] is callback


def test_plot_revision_task_render_prompt_passthrough():
    task = PlotRevisionTask()
    input_data = PlotRevisionInput(
        plot_content="第1章：テスト章",
        findings_yaml="findings: []",
    )

    prompt = task.render_prompt(input_data)
    assert "第1章：テスト章" in prompt


def test_plot_revision_task_execute_calls_client_with_callback():
    task = PlotRevisionTask()
    task.client = MagicMock()
    task.client.generate.return_value = "改稿されたプロット"
    input_data = PlotRevisionInput(
        plot_content="元のプロット", findings_yaml="findings: []"
    )

    callback = MagicMock()
    result = task.execute(input_data, callback=callback)

    assert result == "改稿されたプロット"
    task.client.generate.assert_called_once()
    _args, kwargs = task.client.generate.call_args
    assert kwargs["callback"] is callback
