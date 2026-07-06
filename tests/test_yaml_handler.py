import os

import pytest

from src.utils.yaml_handler import YamlHandler


def test_yaml_handler_load_safe(tmp_path):
    # 存在しないファイル
    assert YamlHandler.load_safe("non_existent_file.yaml") == {}
    assert YamlHandler.load_safe("non_existent_file.yaml", default=[]) == []

    # 正常なファイル
    test_file = tmp_path / "test.yaml"
    test_file.write_text("foo: bar\n", encoding="utf-8")
    assert YamlHandler.load_safe(str(test_file)) == {"foo": "bar"}

    # 壊れたファイル
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("foo: [bar\n", encoding="utf-8")
    assert YamlHandler.load_safe(str(invalid_file)) == {}


def test_yaml_handler_load(tmp_path):
    test_file = tmp_path / "test.yaml"
    test_file.write_text("foo: bar\n", encoding="utf-8")
    assert YamlHandler.load(str(test_file)) == {"foo": "bar"}

    # 壊れたファイルは例外
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("foo: [bar\n", encoding="utf-8")
    import yaml

    with pytest.raises(yaml.YAMLError):
        YamlHandler.load(str(invalid_file))


def test_yaml_handler_load_findings(tmp_path):
    # 通常の findings
    content = "findings:\n  - id: 1\n    text: hello"
    assert YamlHandler.load_findings(content) == [{"id": 1, "text": "hello"}]

    # Markdown の ```yaml 付き
    md_content = "```yaml\nfindings:\n  - id: 2\n    text: world\n```"
    assert YamlHandler.load_findings(md_content) == [{"id": 2, "text": "world"}]

    # リスト形式
    list_content = "- id: 3\n  text: foo"
    assert YamlHandler.load_findings(list_content) == [{"id": 3, "text": "foo"}]

    # ファイルからの読み込み
    test_file = tmp_path / "findings.yaml"
    test_file.write_text(md_content, encoding="utf-8")
    assert YamlHandler.load_findings(str(test_file)) == [{"id": 2, "text": "world"}]


def test_yaml_handler_dump(tmp_path):
    data = {"findings": [{"id": 1, "text": "hello"}]}
    yaml_str = YamlHandler.dump(data)
    assert "hello" in yaml_str
    assert "findings" in yaml_str

    # ファイル書き出し
    test_file = tmp_path / "subdir" / "output.yaml"
    YamlHandler.dump(data, str(test_file))
    assert os.path.exists(str(test_file))
    loaded = YamlHandler.load(str(test_file))
    assert loaded == data
