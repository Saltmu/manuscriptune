import re

from src.utils.ai_tasks.base import AgyTask


class BlockReplacementInput:
    """Input structure for BlockReplacementTask."""

    def __init__(self, context_lines: list[str], findings_in_block: list[dict]):
        self.context_lines = context_lines
        self.findings_in_block = findings_in_block


class BlockReplacementTask(AgyTask[BlockReplacementInput, str | None]):
    """Instructs LLM to rewrite a text block according to the provided review findings."""

    def render_prompt(self, input_data: BlockReplacementInput) -> str:
        context_lines = input_data.context_lines
        findings_in_block = input_data.findings_in_block

        context_text_with_line_numbers = ""
        for idx, line in enumerate(context_lines):
            context_text_with_line_numbers += f"{idx + 1}: {line}"

        findings_str = ""
        for f_idx, f in enumerate(findings_in_block):
            findings_str += f"■ 指摘 {f_idx + 1}\n"
            findings_str += f"・対象原文: {f.get('original')}\n"
            findings_str += f"・指摘内容: {f.get('suggestion')}\n\n"

        prompt = f"""あなたは小説の優秀な編集者です。
以下の【元のテキストブロック】に対して、提示された【修正指示】をすべて反映した、修正後のテキストブロックを生成してください。

【元のテキストブロック】
{context_text_with_line_numbers}

【修正指示】
{findings_str}

【指示・ルール】
・【元のテキストブロック】の各行の先頭には「行番号: 」が付いています。これを参考に、指定された「対象原文」の箇所を修正してください。
・修正する際は、周囲の文脈やキャラクターの口調、文章のリズムに自然に馴染むように書き換えてください。不自然な繋ぎ目にならないように配慮してください。
・出力は、修正・書き換えを行った「テキストブロック全体」としてください。
- 出力するテキストブロックには、行番号（「1: 」など）や、解説、挨拶、マークダウンのコードブロック（```）などは一切含めないでください。純粋な小説の本文のみを出力してください。
・行数は元のテキストブロックとおおむね同程度とし、修正指示に関係のない部分は元の文章をそのまま維持してください。
"""
        return prompt

    def postprocess(
        self, raw_output: str, input_data: BlockReplacementInput
    ) -> str | None:
        result = raw_output.strip()

        # Clean up markdown formatting
        result = re.sub(r"^```[a-zA-Z]*\n", "", result)
        result = re.sub(r"\n```$", "", result).strip()

        # Guard: if LLM output is too short (e.g. LLM failed and returned generic message or empty)
        original_length = sum(len(line) for line in input_data.context_lines)
        if len(result) < original_length * 0.3:
            return None

        # Strip line numbers if the LLM output includes them
        lines = result.splitlines()
        has_line_numbers = all(
            re.match(r"^\d+\s*:\s*", line) for line in lines if line.strip()
        )
        if has_line_numbers and len(lines) > 0:
            cleaned_lines = []
            for line in lines:
                cleaned_line = re.sub(r"^\d+\s*:\s*", "", line)
                cleaned_lines.append(cleaned_line)
            result = "\n".join(cleaned_lines)

        return result
