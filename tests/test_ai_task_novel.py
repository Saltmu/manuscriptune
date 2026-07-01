from unittest.mock import patch

from src.utils.ai_task import (
    NovelPolicyCheckInput,
    NovelPolicyCheckTask,
    NovelRewriteInput,
    NovelRewriteTask,
    NovelSceneWritingInput,
    NovelSceneWritingTask,
    NovelWritingInput,
    NovelWritingTask,
)


@patch("src.utils.ai_task.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_task.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
@patch(
    "src.utils.ai_task.writer_helper.get_novel_setting", return_value="テストタイトル"
)
def test_novel_writing_task_prompt(mock_setting, mock_resolve, mock_read):
    task = NovelWritingTask()
    input_data = NovelWritingInput(
        chapter_title="第1章",
        episode_title="第1話",
        plot_content="テストプロット",
        previous_episode_text="前話の終盤",
        neighbor_plots_block="前後話プロット",
    )

    prompt = task.render_prompt(input_data)
    assert "テストタイトル" in prompt
    assert "第1章" in prompt
    assert "第1話" in prompt
    assert "テストプロット" in prompt
    assert "前話の終盤" in prompt
    assert "前後話プロット" in prompt


@patch("src.utils.ai_task.read_file", return_value="dummy_file_content")
@patch(
    "src.utils.ai_task.writer_helper.resolve_novel_file_by_pattern",
    return_value="dummy_path.txt",
)
def test_novel_scene_writing_task_prompt(mock_resolve, mock_read):
    task = NovelSceneWritingTask()
    input_data = NovelSceneWritingInput(
        chapter_title="第1章",
        episode_title="第1話",
        scene_title="シーン1",
        scene_plot="シーンのプロット",
        context_written="既に書いた本文",
        prev_context_block="前話の終盤",
        novel_title="テストタイトル",
        neighbor_plots_block="前後話プロット",
    )

    prompt = task.render_prompt(input_data)
    assert "テストタイトル" in prompt
    assert "第1章" in prompt
    assert "第1話" in prompt
    assert "シーン1" in prompt
    assert "シーンのプロット" in prompt
    assert "既に書いた本文" in prompt
    assert "前話の終盤" in prompt
    assert "前後話プロット" in prompt

    # Test postprocess with markdown code block removal
    raw_output = "```markdown\n生成された本文\n```"
    processed = task.postprocess(raw_output, input_data)
    assert processed == "生成された本文"


def test_novel_policy_check_task():
    task = NovelPolicyCheckTask()
    input_data = NovelPolicyCheckInput(
        novel_content="小説本文",
        policy_text="ポリシー全体",
        policy_macro_text="ポリシー各章",
        plot_content="演出指示",
    )

    prompt = task.render_prompt(input_data)
    assert "ポリシー全体" in prompt
    assert "ポリシー各章" in prompt
    assert "演出指示" in prompt
    assert "小説本文" in prompt

    # Test postprocess extracting YAML block
    raw_output = (
        "雑談テキスト\n```yaml\nviolations:\n  - original: 'foo'\n```\n雑談テキスト"
    )
    processed = task.postprocess(raw_output, input_data)
    assert "violations:" in processed
    assert "foo" in processed


def test_novel_rewrite_task():
    task = NovelRewriteTask()
    input_data = NovelRewriteInput(
        novel_content="修正前本文",
        yaml_content="指摘事項",
    )

    prompt = task.render_prompt(input_data)
    assert "修正前本文" in prompt
    assert "指摘事項" in prompt

    # Test postprocess
    raw_output = "```\nリライトされた本文\n```"
    processed = task.postprocess(raw_output, input_data)
    assert processed == "リライトされた本文"
