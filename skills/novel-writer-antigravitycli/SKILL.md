---
name: "novel-writer-antigravitycli"
description: "「重天の調律師」シリーズの執筆に特化した小説執筆スキル（Antigravity CLI版）。設定資料、キャラクター概要、プロットに基づき、指定された執筆ポリシーに従って小説を生成します。トークン制限を回避するため、Antigravity CLIツール（agy）を用いてローカルからAPIを呼び出します。"
version: "1.0.0"
category: "Novel-Writing"
input_schema:
  type: "object"
  properties:
    plot: { type: "string" }
    settings: { type: "string" }
    characters: { type: "string" }
    policy: { type: "string" }
  required:
    - plot
    - settings
    - characters
    - policy
output_schema:
  type: "object"
  properties:
    draft_text: { type: "string" }
  required:
    - draft_text
---

# 役割
あなたは「重天の調律師」シリーズの専属作家として機能するエージェントです。提供された設定資料集、キャラクター概要、およびプロットを完全に把握し、指定された「執筆ポリシー」を厳守して物語を綴るスクリプトを呼び出します。

# 参照資料
執筆にあたっては、以下のファイルをスクリプトが自動的に読み込みます。
- **執筆ポリシー:** `data/sources/` 内の全体執筆ポリシー（例：`*執筆ポリシー_全体*.txt`）および第1幕執筆ポリシー（例：`*執筆ポリシー_第1幕*.txt`）
- **設定資料集:** `data/sources/` 内の設定資料集（例：`*設定資料集*.txt`）
- **キャラクター概要:** `data/sources/` 内のキャラクター概要（例：`*キャラクター概要*.txt`）
- **プロット:** `data/sources/` 内のプロット（例：`*第1幕プロット*.txt`）

# 執筆ガイドライン（最重要）
執筆ポリシーに基づき、特に以下の点に注力して執筆が行われます：
1. **文体のリズム:** 同じ語尾の連続（3回以上）を避け、過去形と現在形をミックスし、体言止めを効果的に活用する。
2. **特殊ルビ:** 設定用語や強調したい概念には `|漢字《ルビ》` 形式でルビを振る（例：`|世界の滝《エッジ》`）。
3. **地の文と会話:** 世界観を説明するのではなく、キャラクターの行動やモブとの会話（挨拶や忠告）を通じて「世界の異常性」を浮かび上がらせる。
4. **物理と叙情:** 重力やネフェス圧を、生々しい肉体的苦痛（骨の軋み、呼吸の困難）として描写し、同時に世界の美しさを表現する。

# 使用方法
このスキルはチャット上のAIに直接執筆させるのではなく、専用のPythonスクリプト `writer_cli.py` を通じて Antigravity CLI（`agy`）を呼び出し、モデル（標準では `Gemini 3.5 Flash (High)` など）に執筆させます。

## エージェントへの依頼
「第1章第1話をAntigravity CLIを使って執筆して」や「第2幕第3話をnovel-writer-antigravitycliで書いて」と依頼してください。

エージェントは以下のコマンドを実行します。

```bash
# プロジェクトルートディレクトリ(novel_tools)で実行します
poetry run python skills/novel-writer-antigravitycli/writer_cli.py --episode "第1話"
```

## 出力
- 執筆された小説は、プロジェクトルートの `novels/` フォルダに `1_1.txt` のようなファイル名で自動的に保存されます。
- スクリプトの実行完了後、エージェントは出力されたファイルを読み込んでユーザーに報告します。

> [!IMPORTANT]
> 執筆したテキストは、必要に応じて `novel-formatter` スキル等を併用してウェブ小説向けに整形することを推奨します。
> このスキルを実行するにはシステムに Antigravity CLI（`agy`）がインストールされ、認証情報などが正しく設定されている必要があります。
