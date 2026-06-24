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

本プロジェクトには、小説の執筆、校閲、フォーマットをサポートする **12のエージェントスキル** が用意されています。エージェントに指示を出す際は、各スキルの**キーワード**（`skills/` 配下のディレクトリ名）を参考にしてください。

### 1. 執筆・整形（Writing & Formatting）

- **[Novel-Writer](file:///home/sshioyama/workspace/novel_tools/skills/novel-writer/)** [`novel-writer`]
  「重天の調律師」シリーズの専属作家スキル。設定資料・キャラクター概要・プロットに基づき、執筆ポリシーを厳守して小説を生成します。章単位の執筆指示を受け、エピソードごとに執筆して `novels/` フォルダに保存します。
- **[Novel-Writer-AntigravityCLI](file:///home/sshioyama/workspace/novel_tools/skills/novel_writer_antigravitycli/)** [`novel_writer_antigravitycli`]
  Antigravity CLIツール（agy）経由でローカルからAPIを呼び出し、コンテキスト制限を回避しつつ執筆を行う、CLI環境に最適化された小説執筆スキル。
- **[Novel-Formatter](file:///home/sshioyama/workspace/novel_tools/skills/novel-formatter/)** [`novel-formatter`]
  執筆された小説テキストを、ウェブ小説（カクヨム、なろう等）向けに読みやすく整形（ルビ、改行、三点リーダーなど）します。機械的な前処理とAIによる文脈的調整の2段階で処理します。

### 2. 統合レビュー（Integrated Reviewers）
これらは、複数の個別レビュー観点を統合したメタ（親）スキルです。レビューパイプラインを実行した際、サブエージェントに直接装備されて実行されます。

- **[Logic-Consistency-Reviewer](file:///home/sshioyama/workspace/novel_tools/skills/logic-consistency-reviewer/)** [`logic-consistency-reviewer`]
  世界観設定、過去のプロット・キャラ設定との矛盾、伏線の配置を統合的に検証します（設定監査エージェントが使用）。
- **[Style-Expression-Reviewer](file:///home/sshioyama/workspace/novel_tools/skills/style-expression-reviewer/)** [`style-expression-reviewer`]
  描写力（Show, Don't Tell）、文章のリズム・語彙、キャラクターの口調、構成（ペーシング）を統合的に検証します（文芸表現エージェントが使用）。

### 3. 個別検証・改善（Domain Specific Skills）
これらは、より専門的な校閲・推敲観点に特化した子（個別）スキルです。統合レビュースキルが内部で参照する専門知識としての役割を持ち、またエージェントと直接チャットで特定の側面に絞った指示を出す際にも使用されます。

- **[World-Logic-Guard](file:///home/sshioyama/workspace/novel_tools/skills/world-logic-guard/)** [`world-logic-guard`]
  独自の世界観設定（物理法則、地理、エネルギー体系Nephesなど）との論理的整合性を検証します。フラットアース地理に基づく物理法則への適合などをチェックします。
- **[Consistency-Checker](file:///home/sshioyama/workspace/novel_tools/skills/consistency-checker/)** [`consistency-checker`]
  執筆中の最新シーンと、過去のプロットやキャラクター設定（一人称、外見、属性、タイムライン）との矛盾を検出します。
- **[Foreshadowing-Tracker](file:///home/sshioyama/workspace/novel_tools/skills/foreshadowing-tracker/)** [`foreshadowing-tracker`]
  伏線と情報開示のタイミングを追跡し、後出し設定（Deus ex machina）を防いでカタルシスを最大化します。
- **[Show-Dont-Tell-Enhancer](file:///home/sshioyama/workspace/novel_tools/skills/show-dont-tell-enhancer/)** [`show-dont-tell-enhancer`]
  感情や状況を単に説明（Tell）している箇所を検出し、五感や具体的な行動を用いた描写（Show）へ変換する提案をします。
- **[Rhythm-Vocabulary-Optimizer](file:///home/sshioyama/workspace/novel_tools/skills/rhythm-vocabulary-optimizer/)** [`rhythm-vocabulary-optimizer`]
  文末重複の解消、過剰な接続詞の多用防止、類語の提案などを行い、文章のリズムと語彙力を高めます。
- **[Character-Voice-Checker](file:///home/sshioyama/workspace/novel_tools/skills/character-voice-checker/)** [`character-voice-checker`]
  キャラクターの口調のブレ（ボイスの一貫性）や、シーンをまたぐ感情変化（心理導線）の自然さをチェックします。
- **[Plot-Pacing-Analyzer](file:///home/sshioyama/workspace/novel_tools/skills/plot-pacing-analyzer/)** [`plot-pacing-analyzer`]
  プロットと本文を比較し、物語の進行速度、設定説明（ロアダンプ）による進行停止、展開の駆け足などのペース配分を分析します。

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
poetry run review-server
```
起動後、自動的にブラウザ（デフォルト: `http://localhost:8000`）が開きます。

#### 2. レビューパイプラインとWebUIの一貫起動
特定の小説ファイルのレビュー（フォーマット整形、コンテキスト抽出、並列レビュー、LLM統合）を一括で実行し、完了後に自動的にWebUIを起動して結果を表示したい場合は、以下のコマンドを実行します。
```bash
# 特定の章をレビューして、完了後に自動的にWebUIを起動する場合
poetry run run-review novels/1_12.txt

# 使用するモデルを指定する場合 (デフォルト: Gemini 3.5 Flash (High))
poetry run run-review novels/1_12.txt --model "Gemini 3.5 Flash (High)"

# WebUIサーバーの自動起動をスキップし、CUIでのレビュー実行のみで完了させたい場合
poetry run run-review novels/1_12.txt --no-server
```

---

## ワークフローとマルチエージェントレビュー

包括的な小説レビューを実行するために、本プロジェクトは**「マルチエージェント（設定監査＆文芸表現）」**による並列レビューと、LLMによる自動競合解消（マージ）を採用しています。

### 1. レビュープロセスの実行

1. **前処理 (Formatting)**:
   - **[Novel-Formatter](file:///home/sshioyama/workspace/novel_tools/skills/novel-formatter/)** [`novel-formatter`] を使用して、小説テキストを標準フォーマットに自動整形します。
   - `filter_context.py` を用いて、レビュー対象のテキストに関連するキャラクター設定やプロットなどのコンテキスト情報を抽出します。
2. **サブエージェント並列レビュー (Parallel Review)**:
   メインエージェントが、専門領域に分かれた2つのサブエージェントを並列で起動します：
   * **設定監査エージェント (Logic Auditor)**
     **[Logic-Consistency-Reviewer](file:///home/sshioyama/workspace/novel_tools/skills/logic-consistency-reviewer/)** スキルを適用し、世界観・プロットとの矛盾を検証します。この親スキルは、以下の個別スキルの校閲観点を統合しています：
     - [World-Logic-Guard](file:///home/sshioyama/workspace/novel_tools/skills/world-logic-guard/)（独自設定・地理の監査）
     - [Consistency-Checker](file:///home/sshioyama/workspace/novel_tools/skills/consistency-checker/)（キャラ属性やタイムラインの整合性）
     - [Foreshadowing-Tracker](file:///home/sshioyama/workspace/novel_tools/skills/foreshadowing-tracker/)（伏線の配置チェック）
   * **文芸表現エージェント (Style Editor)**
     **[Style-Expression-Reviewer](file:///home/sshioyama/workspace/novel_tools/skills/style-expression-reviewer/)** スキルを適用し、文章のリズムや描写の魅力を検証します。この親スキルは、以下の個別スキルの校閲観点を統合しています：
     - [Show-Dont-Tell-Enhancer](file:///home/sshioyama/workspace/novel_tools/skills/show-dont-tell-enhancer/)（説明から具体的描写への変換）
     - [Rhythm-Vocabulary-Optimizer](file:///home/sshioyama/workspace/novel_tools/skills/rhythm-vocabulary-optimizer/)（文章のリズムと語彙向上）
     - [Character-Voice-Checker](file:///home/sshioyama/workspace/novel_tools/skills/character-voice-checker/)（口調の一貫性と感情導線）
     - [Plot-Pacing-Analyzer](file:///home/sshioyama/workspace/novel_tools/skills/plot-pacing-analyzer/)（進行ペーシングとロアダンプ過多の検知）
3. **編集長による統合 (Merge & Conflict Resolution)**:
   メインエージェントが双方の指摘結果を分析し、**重複の排除**および**「表現の提案が世界観設定（ロジック）と衝突していないか」の自動調整**を行い、統合された唯一の指摘ファイル `00_integrated_findings.yaml` と、概要レポート `00_integrated_report.md` を出力します。

* `00_integrated_findings.yaml`: **LLMによって競合解消・マージされた最終的な指摘YAML**
* `00_integrated_report.md`: 人間向けの見やすいマークダウンレポート

生成後、WebUI（Novel Studio）の「Editor」を開き、指摘の確認、採用（y/n）の切り替え、および小説本文へのマージ適用（Apply）を行うのが最もスムーズです。

---

### 2. コマンドライン（CLI）での対話的・自動反映（フォールバック）

WebUIを使わずに、コマンドラインから直接反映を実行したい場合や、手動で `00_integrated_findings.yaml` をテキストエディタで編集して反映させたい場合は、以下のPythonスクリプトを使用できます。

```bash
# ターミナル上で1件ずつ確認しながら反映する（手動修正入力も可能）
poetry run apply-findings --dir novel_check_results/1_12 --interactive

# 手動でYAMLを編集して accepted: "y" にしたものを一括自動反映する
poetry run apply-findings --dir novel_check_results/1_12 --auto

# 特定の指摘ID（カンマ区切り）だけを指定して反映する
poetry run apply-findings --dir novel_check_results/1_12 --accept-ids INT-001,INT-003

# LLMを使用せず、指摘内容の「suggestion」から修正文字列を抽出して単純置換する
poetry run apply-findings --dir novel_check_results/1_12 --auto --no-llm
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
