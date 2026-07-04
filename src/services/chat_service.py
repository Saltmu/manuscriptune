import os
import re
from typing import Any

from src.services import novel_service
from src.utils.ai_client import AgyClient
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)


def parse_llm_chat_response(llm_output: str) -> tuple[str, dict[str, str] | None]:
    """Parses LLM output to extract chat reply and optional structured source suggestion."""
    suggestion_pattern = re.compile(
        r"<source_suggestion>(.*?)</source_suggestion>", re.DOTALL
    )
    match = suggestion_pattern.search(llm_output)

    suggestion = None
    reply = llm_output

    if match:
        suggestion_block = match.group(1).strip()
        # Clean reply by removing the source_suggestion block
        reply = suggestion_pattern.sub("", llm_output).strip()

        # Parse suggestion_block
        suggestion_dict = {}
        for line in suggestion_block.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                suggestion_dict[key.strip()] = val.strip()

        # Validate required fields
        required_keys = ["file", "original", "replacement", "reason"]
        if all(k in suggestion_dict for k in required_keys):
            suggestion = {k: suggestion_dict[k] for k in required_keys}

    return reply, suggestion


class ChatService:
    def __init__(self, default_model: str = "Gemini 3.5 Flash (High)"):
        self.default_model = default_model

    def chat(
        self,
        novel_name: str,
        finding_id: str,
        message: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Handles chat interaction for a specific finding."""
        _, yaml_path = novel_service.resolve_paths(novel_name)
        if not yaml_path or not os.path.exists(yaml_path):
            raise ValueError(f"Findings YAML not found for {novel_name}")

        yaml_data = YamlHandler.load(yaml_path)
        findings = yaml_data.get("findings", []) if isinstance(yaml_data, dict) else []

        # Find the specific finding
        finding_item = None
        for f in findings:
            if f.get("id") == finding_id:
                finding_item = f
                break

        if not finding_item:
            raise ValueError(f"Finding with ID {finding_id} not found.")

        # Extract context
        original_text = finding_item.get("original", "")
        suggestion = finding_item.get("suggestion", "")
        analysis = finding_item.get("analysis", "")
        category = finding_item.get("category", "")

        # Get or initialize discussion history
        discussion = finding_item.get("discussion", [])
        if not isinstance(discussion, list):
            discussion = []

        # Append new user message
        discussion.append({"role": "user", "content": message})

        # Build discussion history prompt block
        history_str = ""
        for turn in discussion[:-1]:  # Exclude the latest user message
            role_label = "ユーザー" if turn["role"] == "user" else "アシスタント"
            history_str += f"{role_label}: {turn['content']}\n"

        # Build prompt
        prompt = f"""あなたは小説の編集アシスタントです。
ユーザーは、提示された以下の指摘（レビュー結果）について相談や反論を行っています。

【対象の指摘】
- カテゴリ: {category}
- 対象の本文（原文）: 
\"\"\"
{original_text}
\"\"\"
- 分析内容: {analysis}
- 修正提案: {suggestion}

【これまでの対話履歴】
{history_str or "（なし）"}

【ユーザーの新たな発言】
ユーザー: {message}

上記の文脈を踏まえ、ユーザーに返答してください。
もし対話を通じて、世界観や設定の変更、あるいは小説の方向性についての合意が得られた場合は、ユーザーが手動でマスター設定資料（Google Drive）を修正できるように、以下のフォーマットを必ず含めて応答してください。
直接設定ファイルを修正することはできないため、ユーザーへの手動修正の具体的な提案がゴールです。
設定変更の必要がない場合（単なる日本語表現の調整や、指摘の却下など）は、このフォーマットは出力しないでください。

<source_suggestion>
file: [対象の設定ファイル名、例: キャラクター概要.txt]
original: [修正前の該当記述（設定資料内での原文）]
replacement: [修正後の具体的な記述]
reason: [修正が必要となった理由・背景]
</source_suggestion>
"""

        # Call AI Client
        model_to_use = model or self.default_model
        client = AgyClient(model=model_to_use)
        llm_response = client.generate(prompt)

        # Parse response
        reply, source_suggestion = parse_llm_chat_response(llm_response)

        # Update finding data
        discussion.append({"role": "assistant", "content": reply})
        finding_item["discussion"] = discussion
        if source_suggestion:
            finding_item["source_suggestion"] = source_suggestion
        else:
            finding_item.pop("source_suggestion", None)

        # Save findings back to YAML
        yaml_data["findings"] = findings
        YamlHandler.dump(yaml_data, yaml_path)

        return {
            "status": "success",
            "reply": reply,
            "source_suggestion": source_suggestion,
        }
