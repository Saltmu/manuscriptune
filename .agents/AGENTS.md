# Antigravity 開発・運用ルール

本プロジェクトにおいて、Antigravityが作業およびユーザーとのやり取りを行う際は、以下のルールを遵守してください。

## 1. ユーザーとのやり取りについて
- **日本語でのコミュニケーションの徹底**:
  ユーザーとの対話、作業報告、質問、および提案は、特別な指示がない限りすべて日本語で行ってください。

## 2. PowerShellコマンドの実行と文字コード
- **コンソール出力のUTF-8化**:
  PowerShellコマンドを実行する（`run_command`を使用する）際は、出力の文字化けを防ぐため、コマンドの先頭に必ず `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8;` をプレフィックスとして付加してください。
  （※注意: 各コマンドの実行ツールは毎回独立した新しいPowerShellプロセスで起動されるため、セッションは共有されず、実行ごとに毎回このプレフィックスを付加する必要があります）
  *例*: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; <実際のコマンド>`

- **ファイル入出力時のエンコーディング指定**:
  PowerShellコマンドを使用してファイルの読み書き（`Get-Content`、`Out-File`、`Set-Content`、リダイレクト `>` など）を行う際は、Windowsのデフォルトエンコーディング（Shift_JISやUTF-16）による文字化けを防ぐため、必ず明示的に `-Encoding utf8` などを指定してUTF-8で処理してください。

- **Windows環境でのGitおよびGitHub CLIのパスと認証設定**:
  Windows環境において `git` または `gh` コマンドを使用する際は、コマンドが見つからないエラーや、`git push` 等が資格情報の入力プロンプトで応答待ち（ハング）になるのを防ぐため、以下の対応を必ず行ってください。
  1. コマンド実行前に、セッションの一時的な環境変数 `PATH` に Git および GitHub CLI の標準インストールパスを追加してください。
     *追加コード*: `$env:PATH += ";C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI"`
  2. Git操作（特にプッシュ等）を行う前には、資格情報エラーを防ぐために `gh auth setup-git` を実行してください。
  
  *例（Gitプッシュ時のワンライナー）*:
  `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PATH += ";C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI"; gh auth setup-git; git push origin <branch_name>`

## 3. Pythonの実行環境について
- **Poetry環境の利用**:
  Pythonスクリプトを実行する際は、依存関係の不整合を防ぐため、グローバル環境ではなくPoetryを使用し、`poetry run python <script.py>` の形式で実行するか、あるいはプロジェクト内の仮想環境（`venv`）をアクティベートして実行してください。

## 4. 小説の執筆・レビュー時の設定資料参照
- **参照資料（`data/sources/`）への準拠**:
  小説の執筆、レビュー、修正適用などのすべての作業において、`data/sources/` 配下にある設定資料・プロット・キャラクター概要を最優先のソース（真実の基準）として参照してください。推測や独自の判断で世界観設定、歴史、キャラクターの口調・設定を捏造または逸脱させてはなりません。

## 5. YAMLレビューレポートの形式遵守
- **レビュー結果のスキーマと反映ルール**:
  `/novel_review_pipeline` などのレビュー結果を格納するYAMLファイルを生成・更新する際は、プロジェクト規定のスキーマ（`findings` 配下の `id`, `location`, `original`, `category`, `severity`, `analysis`, `suggestion`, `accepted` 等）を厳格に維持してください。
  指摘を小説テキストに自動反映する際は、ユーザーが `accepted: "y"` とマークした指摘のみを正確に反映し、`accepted: "n"` またはその他の項目は変更しないようにしてください。また、反映時は文脈の自然さや執筆ポリシーに留意してください。
- **レビュー結果の確認・適用（WEBUI優先ルール）**:
  ユーザーから「レビュー結果を反映して」「レビュー結果を見せて」「推敲内容を確認したい」などの指示を受けた場合は、チャット上で指摘リストを展開して対話的に適用するのではなく、WebUIである **「Novel Studio (WebUI)」** を通じてブラウザ上で確認・適用することを案内してください。
  WebUIサーバーがまだ起動していない場合は、`poetry run python src/review_server.py` を実行して起動し、ユーザーにブラウザを開くよう促してください。
  （※例外的に、ユーザーがCUIやチャット上での直接反映を明示的に望む場合は、`poetry run python src/apply_findings.py` スクリプトを使用して反映を行ってください。エージェントがテキストを手動で直接編集して置換することは避けてください）

- **レビューパイプライン実行とWebUI連携**:
  ユーザーから特定の小説（例: `novels/1_12.txt`）のレビューを求められた場合は、`poetry run python src/run_review_pipeline.py novels/<filename>` を実行してください。このコマンドは、並列レビューとLLM統合を行った後、自動的にWebUIサーバーを起動し、ブラウザを開きます。完了後はWebUI上で指摘の確認と適用を行うようユーザーに案内してください。

