# Novel Tools

「重天の調律師」シリーズの執筆・校閲・フォーマットを支援するエージェント環境です。

## プロジェクト構成

```
novel_tools/
├── novels/                   # 執筆済み小説テキスト（章-話.txt 形式）
├── novel_check_results/      # レビュー結果の保存先（章-話ごとのサブフォルダ）
├── data/sources/             # 執筆参照資料（設定資料集・プロット・キャラ概要）
├── skills/                   # エージェントスキル群
└── .agents/workflows/        # 定義済みワークフロー
```

## スキル構成

本プロジェクトには、小説執筆をサポートする **12のエージェントスキル** が用意されています。エージェントに指示を出す際は、各スキルの**キーワード**を添えて呼び出してください。

### 1. Writing（執筆）

- **Novel-Writer** [`novel-writer`]
  「重天の調律師」シリーズの専属作家スキル。設定資料・キャラクター概要・プロットに基づき、執筆ポリシーを厳守して小説を生成する。章単位の執筆指示を受け、エピソードごとに執筆して `novels/` フォルダに保存する。
- **Novel-Writer (Antigravity CLI版)** [`novel_writer_antigravitycli`]
  Antigravity CLI環境との連携に最適化された小説執筆スキル。

### 2. Formatting（フォーマット調整）

- **Novel-Formatter** [`novel-formatter`]
  執筆された小説テキストを、ウェブ小説（カクヨム、なろう等）向けに読みやすくフォーマットする。機械的な前処理とAIによる文脈的調整の2段階で処理する。

## WebUI ポータル「Novel Studio」の利用

本プロジェクトでは、小説の執筆、レビュー、指摘の確認および本文への反映を直感的に行えるWebベースの総合開発ポータル **「Novel Studio」** を提供しています。

### Novel Studio で提供される機能
1. **ダッシュボード**: 執筆済み小説テキストの一覧表示、レビュー実行状況や最終更新日時の確認。
2. **AI執筆支援 (Write)**: 指定したエピソード名、プロット、キャラクター概要、執筆ポリシー等を選択し、AIによる小説執筆をWebUI上で実行（進捗ログをリアルタイムでSSEストリーミング出力）。
3. **設定同期 (Sync)**: 設定資料・プロット等のGoogle Driveフォルダとの同期をワンクリックで実行（SSEストリーミング出力）。
4. **並列校閲 (Review)**: 選択した小説に対して「設定監査 (Logic)」と「文芸表現 (Style)」の並列レビューをWebUI上から実行。
5. **インタラクティブ校閲エディタ (Editor)**:
   - 小説本文とAIによる統合指摘（`00_integrated_findings.yaml`）を並べて表示。
   - 指摘の重要度（Severity）やカテゴリによるフィルタリング。
   - 指摘ごとの採用 (`accepted: y/n`) の切り替え、およびその場での提案内容の修正保存。
   - 「採用した指摘の一括反映 (Apply)」を実行し、本文ファイル（`01_formatted.txt`）へ自動でマージ適用。

---

### 起動方法

#### 1. WebUIサーバー単体の起動
小説の選択、新規執筆、Google Driveとの同期、既存のレビュー結果の確認や適用を行う場合は、以下のコマンドでWebUIサーバーを起動します。
```bash
poetry run python src/review_server.py
```
起動後、自動的にブラウザ（デフォルト: `http://localhost:8000`）が開きます。

#### 2. レビューパイプラインとWebUIの一貫起動
特定の小説ファイルのレビュー（フォーマット整形、コンテキスト抽出、並列レビュー、LLM統合）を一括で実行し、完了後に自動的にWebUIを起動して結果を表示したい場合は、以下のコマンドを実行します。
```bash
# 特定の章をレビューして、完了後に自動的にWebUIを起動する場合
poetry run python src/run_review_pipeline.py novels/1_12.txt

# 使用するモデルを指定する場合 (デフォルト: Gemini 3.5 Flash (High))
poetry run python src/run_review_pipeline.py novels/1_12.txt --model "Gemini 3.5 Flash (High)"

# WebUIサーバーの自動起動をスキップし、CUIでのレビュー実行のみで完了させたい場合
poetry run python src/run_review_pipeline.py novels/1_12.txt --no-server
```

---

## ワークフローとマルチエージェントレビュー

包括的な小説レビューを実行するために、本プロジェクトは**「マルチエージェント（設定監査＆文芸表現）」**による並列レビューと、LLMによる自動競合解消（マージ）を採用しています。

### 1. レビュープロセスの実行

1. **前処理**: `novel-formatter` によるフォーマット整形と、`filter_context.py` による関連設定情報の事前抽出。
2. **サブエージェント並列レビュー**: 
   メインエージェントが2つの専門サブエージェントを並列で起動します：
   * **設定監査エージェント (Logic Auditor)**: `logic-consistency-reviewer` を使用し、設定やプロットとの矛盾、伏線の配置を検証します。
   * **文芸表現エージェント (Style Editor)**: `style-expression-reviewer` を使用し、描写力・リズム・口調・ペーシングを検証します。
3. **編集長による統合 (マージ＆競合解消)**:
   メインエージェントが双方の指摘結果を分析し、**重複の排除**および**「表現の提案が世界観設定（ロジック）と衝突していないか」の自動調整**を行い、統合された唯一の指摘ファイル `00_integrated_findings.yaml` と、概要レポート `00_integrated_report.md` を出力します。
* `00_integrated_findings.yaml`: **LLMによって競合解消・マージされた最終的な指摘YAML**
* `00_integrated_report.md`: 人間向けの見やすいマークダウンレポート

生成後、WebUI（Novel Studio）の「Editor」を開き、指摘の確認、採用（y/n）の切り替え、および小説本文へのマージ適用（Apply）を行うのが最もスムーズです。

---

### 2. コマンドライン（CLI）での対話的・自動反映（フォールバック）

WebUIを使わずに、コマンドラインから直接反映を実行したい場合や、手動で `00_integrated_findings.yaml` をテキストエディタで編集して反映させたい場合は、以下のPythonスクリプトを使用できます。

```bash
# ターミナル上で1件ずつ確認しながら反映する（手動修正入力も可能）
poetry run python src/apply_findings.py --dir novel_check_results/1_12 --interactive

# 手動でYAMLを編集して accepted: "y" にしたものを一括自動反映する
poetry run python src/apply_findings.py --dir novel_check_results/1_12 --auto

# 特定の指摘ID（カンマ区切り）だけを指定して反映する
poetry run python src/apply_findings.py --dir novel_check_results/1_12 --accept-ids INT-001,INT-003

# LLMを使用せず、指摘内容の「suggestion」から修正文字列を抽出して単純置換する
poetry run python src/apply_findings.py --dir novel_check_results/1_12 --auto --no-llm
```

#### レビュー結果のYAML構造

統合された指摘は以下の共通スキーマに従って出力されます：

```yaml
findings:
  - id: "INT-001"              # 統合(Integrated)を示すID＋連番
    location: "8行目"          # 該当箇所
    original: "「原文の抜粋」"  # 対象テキスト
    category: "設定矛盾"       # 指摘のカテゴリ
    severity: "high"           # high / medium / low / info
    analysis: "競合が解消された分析・理由の詳細"
    suggestion: "設定を考慮して調整された修正提案"
    accepted: "n"              # ← WebUIまたはテキストエディタで "y" に変更すると採用
```

## 参照資料（data/sources/）

| ファイル                          | 内容                                 |
| --------------------------------- | ------------------------------------ |
| `00_執筆ポリシーver.2.txt`        | 文体・ルビ・描写ルール等の執筆方針   |
| `01_重天の調律師_設定資料集.txt`  | 世界観・魔法体系・地理等の設定資料集 |
| `02_創世記から現代まで.txt`       | 世界の歴史年表                       |
| `03-1_第１幕キャラクター概要.txt` | 第1幕登場キャラクターの詳細          |
| `04-1_第1幕プロットver.2.txt`     | 第1幕の詳細プロット                  |
| `04_大枠プロット.txt`             | シリーズ全体の大枠プロット           |

## セットアップ

### 1. 依存関係のインストール

本プロジェクトは **Poetry** を使用してパッケージと仮想環境の管理を行っています。以下のコマンドで必要な依存関係をインストールします。

```bash
poetry install
```

### 2. 設定ファイルの準備

1. `antigravity.yaml.example` を `antigravity.yaml` にコピーします。
   ```bash
   cp antigravity.yaml.example antigravity.yaml
   ```
2. `antigravity.yaml` を編集し、`folder_id` や `auth_file` のパスを自身の環境に合わせて設定してください。
   > [!IMPORTANT]
   > `antigravity.yaml` には機密情報が含まれるため、Gitにはコミットしないよう `.gitignore` で設定されています。
