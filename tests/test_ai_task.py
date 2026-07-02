import os
from unittest.mock import MagicMock, patch

import pytest

from src.utils.ai_task import (
    BlockReplacementInput,
    BlockReplacementTask,
    FindingsIntegrationInput,
    FindingsIntegrationTask,
    ReviewSkillInput,
    ReviewSkillTask,
)


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.generate.return_value = "Generated Output"
    return client


def test_review_skill_task_prompt_and_postprocess(tmp_path, mock_client):
    # Set up dummy skill structure
    skills_dir = tmp_path / "skills" / "dummy-skill"
    skills_dir.mkdir(parents=True)
    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text("Dummy Instruction", encoding="utf-8")

    # Mock os.path.exists and open to point to our temp directory for skills
    original_exists = os.path.exists

    def mock_exists(path):
        if "skills/dummy-skill/SKILL.md" in path.replace("\\", "/"):
            return True
        return original_exists(path)

    # Prepare input
    input_data = ReviewSkillInput(
        skill_name="dummy-skill",
        target_text="Target Novel Content",
        output_dir=str(tmp_path),
    )

    task = ReviewSkillTask(client=mock_client)

    with (
        patch("os.path.exists", mock_exists),
        patch("src.utils.ai_tasks.review.read_file", return_value="Dummy Instruction"),
    ):
        prompt = task.render_prompt(input_data)
        assert "Dummy Instruction" in prompt
        assert "Target Novel Content" in prompt

        # Test postprocessing extraction of yaml blocks
        mock_client.generate.return_value = "```yaml\nfindings: []\n```"
        result = task.execute(input_data)
        assert result == "findings: []"


def test_block_replacement_task_postprocess(mock_client):
    context_lines = [
        "第一章\n",
        "少年は佇んでいた。\n",
        "古い楽器が手にある。\n",
    ]
    findings = [
        {
            "id": "INT-001",
            "original": "古い楽器",
            "suggestion": "「歴史を感じさせる弦楽器」に修正",
        }
    ]
    input_data = BlockReplacementInput(
        context_lines=context_lines, findings_in_block=findings
    )

    task = BlockReplacementTask(client=mock_client)

    # Check prompt rendering
    prompt = task.render_prompt(input_data)
    assert "第一章" in prompt
    assert "古い楽器" in prompt

    # Test normal postprocess
    mock_client.generate.return_value = (
        "1: 第一章\n2: 少年は佇んでいた。\n3: 歴史を感じさせる弦楽器が手にある。"
    )
    result = task.execute(input_data)
    assert "歴史を感じさせる弦楽器" in result
    assert "1:" not in result  # Line numbers should be stripped

    # Test reject due to too short output
    mock_client.generate.return_value = "Short"
    result = task.execute(input_data)
    assert result is None  # Should be rejected


def test_findings_integration_task(mock_client):
    target_text = "Target Text"
    raw_findings_text = "Raw Findings"
    input_data = FindingsIntegrationInput(
        target_text=target_text, raw_findings_text=raw_findings_text
    )

    task = FindingsIntegrationTask(client=mock_client)

    prompt = task.render_prompt(input_data)
    assert "Target Text" in prompt
    assert "Raw Findings" in prompt

    mock_client.generate.return_value = "```yaml\nfindings:\n  - id: INT-001\n```"
    result = task.execute(input_data)
    assert result == "findings:\n  - id: INT-001"


def test_review_skill_task_contexts(tmp_path, mock_client):
    skills = [
        "text-reviewer-logic",
        "text-reviewer-style",
        "plot-reviewer-conflict",
        "plot-reviewer-structure",
    ]
    for skill in skills:
        skills_dir = tmp_path / "skills" / skill
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text(f"Instruction for {skill}", encoding="utf-8")

    task = ReviewSkillTask(client=mock_client)

    # We patch os.path.exists to return True for dummy SKILL.md paths
    original_exists = os.path.exists

    def mock_exists(path):
        normalized = path.replace("\\", "/")
        if any(f"skills/{skill}/SKILL.md" in normalized for skill in skills):
            return True
        return original_exists(path)

    with (
        patch("os.path.exists", mock_exists),
        patch(
            "src.utils.ai_tasks.review.read_file",
            side_effect=lambda path: f"Instruction for {os.path.basename(os.path.dirname(path))}",
        ),
        patch(
            "src.utils.ai_tasks.review.ReviewSkillTask._get_text_logic_context",
            return_value="Logic Context Block",
        ) as mock_logic,
        patch(
            "src.utils.ai_tasks.review.ReviewSkillTask._get_text_style_context",
            return_value="Style Context Block",
        ) as mock_style,
        patch(
            "src.utils.ai_tasks.review.ReviewSkillTask._get_plot_conflict_context",
            return_value="Conflict Context Block",
        ) as mock_conflict,
        patch(
            "src.utils.ai_tasks.review.ReviewSkillTask._get_plot_structure_context",
            return_value="Structure Context Block",
        ) as mock_structure,
    ):
        # 1. logic
        input_data = ReviewSkillInput(
            "text-reviewer-logic", "Target Content", str(tmp_path)
        )
        prompt = task.render_prompt(input_data)
        assert "Logic Context Block" in prompt
        mock_logic.assert_called_once()

        # 2. style
        input_data = ReviewSkillInput(
            "text-reviewer-style", "Target Content", str(tmp_path)
        )
        prompt = task.render_prompt(input_data)
        assert "Style Context Block" in prompt
        mock_style.assert_called_once()

        # 3. conflict
        input_data = ReviewSkillInput(
            "plot-reviewer-conflict", "Target Content", str(tmp_path)
        )
        prompt = task.render_prompt(input_data)
        assert "Conflict Context Block" in prompt
        mock_conflict.assert_called_once()

        # 4. structure
        input_data = ReviewSkillInput(
            "plot-reviewer-structure", "Target Content", str(tmp_path)
        )
        prompt = task.render_prompt(input_data)
        assert "Structure Context Block" in prompt
        mock_structure.assert_called_once()
