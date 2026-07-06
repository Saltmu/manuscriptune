import os
import re

from src.utils import project_config as writer_helper
from src.utils.ai_tasks.base import AgyTask
from src.utils.file_io import read_file

_CONTEXT_BUILDERS = {
    "text-reviewer-logic": "_get_text_logic_context",
    "text-reviewer-style": "_get_text_style_context",
    "plot-reviewer-conflict": "_get_plot_conflict_context",
    "plot-reviewer-structure": "_get_plot_structure_context",
}


class ReviewSkillInput:
    """Input structure for ReviewSkillTask."""

    def __init__(self, skill_name: str, target_text: str, output_dir: str):
        self.skill_name = skill_name
        self.target_text = target_text
        self.output_dir = output_dir


class ReviewSkillTask(AgyTask[ReviewSkillInput, str]):
    """Executes a specific review skill to check novel content and return YAML findings."""

    def render_prompt(self, input_data: ReviewSkillInput) -> str:
        skill_name = input_data.skill_name
        target_text = input_data.target_text
        output_dir = input_data.output_dir

        skill_md_path = os.path.join("skills", skill_name, "SKILL.md")
        if not os.path.exists(skill_md_path):
            raise FileNotFoundError(
                f"SKILL.md not found for skill '{skill_name}' at {skill_md_path}"
            )

        skill_instruction = read_file(skill_md_path)

        def get_latest_file(pattern_key: str, default_pattern: str) -> str | None:
            return writer_helper.resolve_novel_file_by_pattern(  # type: ignore[no-any-return]
                pattern_key, default_pattern, None
            )

        method_name = _CONTEXT_BUILDERS.get(skill_name)
        if method_name:
            builder = getattr(self, method_name)
            context_text = builder(get_latest_file, output_dir)
        else:
            context_text = ""

        target_label = (
            "【校閲対象のプロットテキスト】"
            if skill_name.startswith("plot-")
            else "【校閲対象の小説テキスト】"
        )

        prompt = f"""{skill_instruction}

==============================
{context_text}
==============================

==============================
{target_label}
{target_text}
==============================

【実行指示】
上記のテキストに対し、あなたの役割に従って校閲を行ってください。
指摘事項がある場合は、指定されたYAML形式で出力してください。
・出力は必ず ```yaml で始まるYAMLコードブロックのみにしてください。
・挨拶や解説などのメタなテキストは一切出力しないでください。
・もし指摘事項がない場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```
"""
        return prompt

    def _get_text_logic_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        filtered_context_path = os.path.join(output_dir, "01_filtered_context.txt")
        if os.path.exists(filtered_context_path):
            context_text += f"\n【フィルタリング済み設定資料】\n{read_file(filtered_context_path)}\n"
        else:
            setting_file = get_latest_file("settings", "*設定資料集*.txt")
            char_file = get_latest_file("character", "*キャラクター概要*.txt")
            plot_file = get_latest_file("plot", "*プロット*.txt")
            if setting_file:
                context_text += f"\n【設定資料集】\n{read_file(setting_file)}\n"
            if char_file:
                context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
            if plot_file:
                context_text += f"\n【プロット】\n{read_file(plot_file)}\n"
        return context_text

    def _get_text_style_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        policy_file = get_latest_file("policy_global", "*執筆ポリシー_全体*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if policy_file:
            context_text += f"\n【執筆ポリシー】\n{read_file(policy_file)}\n"
        return context_text

    def _get_plot_conflict_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        policy_file = get_latest_file("policy_global", "*執筆ポリシー_全体*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if policy_file:
            context_text += f"\n【執筆ポリシー】\n{read_file(policy_file)}\n"
        return context_text

    def _get_plot_structure_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        setting_file = get_latest_file("settings", "*設定資料集*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if setting_file:
            context_text += f"\n【設定資料集】\n{read_file(setting_file)}\n"
        return context_text

    def postprocess(self, raw_output: str, input_data: ReviewSkillInput) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


class FindingsIntegrationInput:
    """Input structure for FindingsIntegrationTask."""

    def __init__(self, target_text: str, raw_findings_text: str):
        self.target_text = target_text
        self.raw_findings_text = raw_findings_text


class FindingsIntegrationTask(AgyTask[FindingsIntegrationInput, str]):
    """Merges and resolves conflicts from multiple raw finding lists into a consolidated YAML."""

    def render_prompt(self, input_data: FindingsIntegrationInput) -> str:
        target_text = input_data.target_text
        raw_findings_text = input_data.raw_findings_text

        prompt = f"""あなたは小説の編集長です。
校閲エージェントから提出された同一の小説章に対する校閲指摘リスト（YAML）を精査し、以下のルールに従って1つの統合された指摘リスト（YAML）を作成してください。

【マージルール】
1. **重複の排除**: 同じ箇所の同じような指摘は、最も具体的で有益な内容に統合してください。
2. **競合の解決**: 表現側の提案が世界観やキャラクター設定に反している場合は、設定側のルールを最優先し、表現側の提案を設定に矛盾しないように調整または棄却してください。
3. **重要度による絞り込み**: 優先順位（severity: high > medium > low）を考慮し、重要度の低い些細な指摘は削除し、全体で最大20〜25件程度に抑えてください。
4. **IDの振り直し**: 統合後の指摘に対して、`INT-001`, `INT-002` ... と連番でIDを振り直してください。
5. **出力フォーマット**:
   - 必ず `findings` キーを持つ配列形式のYAMLコードブロック（```yaml ... ```）のみを出力してください。
   - 挨拶や解説などのメタなテキストは一切出力しないでください。
   - 各 finding の構造は以下のキーを厳密に保持してください：
     - `id` (INT-XXX)
     - `location` (元の指摘の行数)
     - `original` (該当箇所のテキスト抜粋。元の指摘リストにある `original` や【校閲対象の小説テキスト】から、一切の改変（文字の追加、削除、表現の翻訳、誤植 of 修正、勝手な省略など）をせず、一字一句違わずにそのままコピーして抽出してください。「カップの縁」を「カップ of 縁」と表現を変えるなどの改変は絶対に禁止します)
     - `category` (カテゴリ名)
     - `severity` (high / medium / low / info)
     - `analysis` (統合・競合解決された分析内容)
     - `suggestion` (統合・調整された修正案)
     - `accepted` ("n" で固定)

もし指摘事項がなくなった場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```

【校閲対象の小説テキスト】
==============================
{target_text}
==============================

【検出された校閲指摘リスト】
==============================
{raw_findings_text}
==============================
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: FindingsIntegrationInput) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


class PlotFindingsIntegrationInput:
    """Input structure for PlotFindingsIntegrationTask."""

    def __init__(self, target_text: str, raw_findings_text: str):
        self.target_text = target_text
        self.raw_findings_text = raw_findings_text


class PlotFindingsIntegrationTask(AgyTask[PlotFindingsIntegrationInput, str]):
    """Merges and resolves conflicts from multiple raw plot finding lists into a consolidated YAML."""

    def render_prompt(self, input_data: PlotFindingsIntegrationInput) -> str:
        target_text = input_data.target_text
        raw_findings_text = input_data.raw_findings_text

        prompt = f"""あなたはプロットの構成監修者です。
校閲エージェントから提出された同一のプロットに対する校閲指摘リスト（YAML）を精査し、以下のルールに従って1つの統合された指摘リスト（YAML）を作成してください。

【マージルール】
1. **重複の排除**: 同じ箇所の同じような指摘は、最も具体的で有益な内容に統合してください。
2. **設定との一貫性**: 指摘や提案内容が世界観やキャラクター設定に反している場合は、設定側のルールを最優先し、それに矛盾しないように調整または棄却してください。
3. **重要度による絞り込み**: 優先順位（severity: high > medium > low）を考慮し、重要度の低い些細な指摘は削除し、全体で最大20〜25件程度に抑えてください。
4. **IDの振り直し**: 統合後の指摘に対して、`PINT-001`, `PINT-002` ... と連番でIDを振り直してください。
5. **出力フォーマット**:
   - 必ず `findings` キーを持つ配列形式のYAMLコードブロック（```yaml ... ```）のみを出力してください。
   - 挨拶や解説などのメタなテキストは一切出力しないでください。
   - 各 finding の構造は以下のキーを厳密に保持してください：
     - `id` (PINT-XXX)
     - `location` (元の指摘の場所・シーン名等)
     - `original` (該当箇所のテキスト抜粋。元の指摘リストにある `original` や【校閲対象 of プロットテキスト】から、一切の改変（文字の追加、削除、表現の翻訳、誤植の修正、勝手な省略など）をせず、一字一句違わずにそのままコピーして抽出してください)
     - `category` (カテゴリ名)
     - `severity` (high / medium / low / info)
     - `analysis` (統合・競合解決された分析内容)
     - `suggestion` (統合・調整された修正案)
     - `accepted` ("n" で固定)

もし指摘事項がなくなった場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```

【校閲対象のプロットテキスト】
==============================
{target_text}
==============================

【検出された校閲指摘リスト】
==============================
{raw_findings_text}
==============================
"""
        return prompt

    def postprocess(
        self, raw_output: str, input_data: PlotFindingsIntegrationInput
    ) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result
