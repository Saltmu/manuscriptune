import os
import re
from typing import Any, cast

import yaml


class YamlHandler:
    @staticmethod
    def load(filepath: str) -> Any:
        """YAMLファイルを読み込み、Pythonオブジェクトとして返します。

        ファイルが存在しない、あるいはパースに失敗した場合は例外を送出します。
        """
        with open(filepath, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def load_safe(filepath: str, default: Any = None) -> Any:
        """安全にYAMLファイルを読み込みます。

        ファイルが存在しない、またはパースに失敗した場合はデフォルト値を返します。
        """
        if default is None:
            default = {}
        if not os.path.exists(filepath):
            return default
        try:
            with open(filepath, encoding="utf-8") as f:
                return yaml.safe_load(f) or default
        except Exception:
            return default

    @staticmethod
    def load_findings(filepath_or_content: str) -> list[dict[Any, Any]]:
        """ファイルパスまたはYAML文字列から指摘のリストをロードします。

        Markdownのコードブロック (```yaml ... ```)
        が含まれている場合は自動的に除去し、
        "findings"キーやその他のリスト構造から指摘データを抽出します。
        """
        try:
            if os.path.exists(filepath_or_content):
                with open(filepath_or_content, encoding="utf-8") as f:
                    content = f.read()
            else:
                content = filepath_or_content

            if not content:
                return []

            # Markdown ```yaml ... ``` の除去
            sanitized = re.sub(r"```yaml\s*([\s\S]*?)```", r"\1", content).strip()
            data = yaml.safe_load(sanitized)

            if isinstance(data, dict):
                if "findings" in data:
                    return cast(list[dict[Any, Any]], data["findings"])
                # 辞書の中で値がリストになっている最初の要素を返す
                for v in data.values():
                    if isinstance(v, list):
                        return cast(list[dict[Any, Any]], v)
                return []
            elif isinstance(data, list):
                return cast(list[dict[Any, Any]], data)
        except Exception as e:
            from src.utils.logger import get_logger

            logger = get_logger("YamlHandler")
            logger.warning(f"Failed to parse YAML: {e}")
        return []

    @staticmethod
    def dump(data: dict | list, filepath: str | None = None) -> str:
        """データをYAML形式にシリアライズします。

        filepathが指定されている場合は、そのパスに書き込みます。 常に allow_unicode=True,
        default_flow_style=False でダンプします。
        """
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        if filepath:
            # 親ディレクトリが存在しない場合は作成する
            dir_path = os.path.dirname(os.path.abspath(filepath))
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(yaml_str)
        return yaml_str
