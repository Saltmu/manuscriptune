import os
import tempfile

import pytest

from src.utils.skill_registry import SkillRegistry, SkillValidationError, SkillValidator


def test_compare_versions():
    # >= 比較
    assert SkillValidator.compare_versions("1.2.3", ">=1.0.0") is True
    assert SkillValidator.compare_versions("1.2.3", ">=1.2.3") is True
    assert SkillValidator.compare_versions("1.2.3", ">=1.3.0") is False

    # <= 比較
    assert SkillValidator.compare_versions("1.2.3", "<=2.0.0") is True
    assert SkillValidator.compare_versions("1.2.3", "<=1.2.3") is True
    assert SkillValidator.compare_versions("1.2.3", "<=1.0.0") is False

    # == 比較
    assert SkillValidator.compare_versions("1.2.3", "==1.2.3") is True
    assert SkillValidator.compare_versions("1.2.3", "1.2.3") is True
    assert SkillValidator.compare_versions("1.2.3", "==1.2.4") is False

    # ^ 比較
    assert SkillValidator.compare_versions("1.2.3", "^1.0.0") is True
    assert SkillValidator.compare_versions("1.2.3", "^1.2.3") is True
    assert SkillValidator.compare_versions("2.0.0", "^1.0.0") is False
    assert SkillValidator.compare_versions("0.2.3", "^0.2.0") is True
    assert SkillValidator.compare_versions("0.3.0", "^0.2.0") is False
    assert SkillValidator.compare_versions("0.0.3", "^0.0.2") is False


def test_validate_frontmatter_valid():
    valid_fm = {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "category": "Test",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"result": {"type": "string"}},
        },
    }
    # 例外がスローされないこと
    SkillValidator.validate_frontmatter(valid_fm)


def test_validate_frontmatter_invalid():
    # 必須キー欠損
    invalid_fm = {"name": "test-skill", "version": "1.0.0"}
    with pytest.raises(SkillValidationError) as exc_info:
        SkillValidator.validate_frontmatter(invalid_fm)
    assert "Missing required field" in str(exc_info.value)

    # 不正なスキーマ
    invalid_schema = {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "test",
        "input_schema": "not-a-dict",  # dictであるべき
        "output_schema": {},
    }
    with pytest.raises(SkillValidationError) as exc_info:
        SkillValidator.validate_frontmatter(invalid_schema)
    assert "must be a dictionary" in str(exc_info.value)


def test_skill_registry_validation():
    # 一時ディレクトリにテスト用スキルを作成してテスト
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 正常なスキルA
        skill_a_dir = os.path.join(tmpdir, "skill-a")
        os.makedirs(skill_a_dir)
        with open(os.path.join(skill_a_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("""---
name: "skill-a"
version: "1.0.0"
description: "Skill A"
input_schema:
  type: "object"
output_schema:
  type: "object"
---
# Main content
""")

        # 2. 正常なスキルB（Aに依存）
        skill_b_dir = os.path.join(tmpdir, "skill-b")
        os.makedirs(skill_b_dir)
        with open(os.path.join(skill_b_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("""---
name: "skill-b"
version: "1.2.0"
description: "Skill B"
dependencies:
  - name: "skill-a"
    version: "^1.0.0"
input_schema:
  type: "object"
output_schema:
  type: "object"
---
# Main content
""")

        registry = SkillRegistry()
        # ロードして依存関係チェック
        skills = registry.load_skills(tmpdir)
        assert "skill-a" in skills
        assert "skill-b" in skills

        # 依存関係チェックがパスすること
        registry.check_dependencies(skills)


def test_skill_registry_dependency_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        # スキルBだけ作成（Aに依存しているが存在しない）
        skill_b_dir = os.path.join(tmpdir, "skill-b")
        os.makedirs(skill_b_dir)
        with open(os.path.join(skill_b_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("""---
name: "skill-b"
version: "1.2.0"
description: "Skill B"
dependencies:
  - name: "skill-a"
    version: "^1.0.0"
input_schema:
  type: "object"
output_schema:
  type: "object"
---
# Main content
""")

        registry = SkillRegistry()
        skills = registry.load_skills(tmpdir)
        with pytest.raises(SkillValidationError) as exc_info:
            registry.check_dependencies(skills)
        assert "Dependency 'skill-a' not found" in str(exc_info.value)


def test_skill_registry_dependency_version_mismatch():
    with tempfile.TemporaryDirectory() as tmpdir:
        # スキルA (version 2.0.0)
        skill_a_dir = os.path.join(tmpdir, "skill-a")
        os.makedirs(skill_a_dir)
        with open(os.path.join(skill_a_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("""---
name: "skill-a"
version: "2.0.0"
description: "Skill A"
input_schema:
  type: "object"
output_schema:
  type: "object"
---
# Main content
""")

        # スキルB（Aの ^1.0.0 に依存）
        skill_b_dir = os.path.join(tmpdir, "skill-b")
        os.makedirs(skill_b_dir)
        with open(os.path.join(skill_b_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("""---
name: "skill-b"
version: "1.2.0"
description: "Skill B"
dependencies:
  - name: "skill-a"
    version: "^1.0.0"
input_schema:
  type: "object"
output_schema:
  type: "object"
---
# Main content
""")

        registry = SkillRegistry()
        skills = registry.load_skills(tmpdir)
        with pytest.raises(SkillValidationError) as exc_info:
            registry.check_dependencies(skills)
        assert "Version requirement '^1.0.0' for 'skill-a' not met" in str(
            exc_info.value
        )
