# 2026-07-06 Orchestune dispatch GitHub Actions導入 障害記録

GitHub Actionsによる`dispatch-cycle`の定期実行を導入する過程で発生した一連の障害と対応の記録。
今後同種の作業をする際の参考、および再発防止のための運用ルール策定の根拠として残す。

## 経緯サマリー

| # | 内容 | 対応PR/Issue |
| --- | --- | --- |
| 1 | `.github/workflows/orchestune-dispatch.yml`を新規追加（毎時dispatch） | Issue #227 / PR #228 |
| 2 | 初回手動実行で2件の不具合が発覚（後述） | PR #229（当初#228に含める予定が、マージタイミングのずれで別PR化） |
| 3 | ラベル未作成によりdispatchが機能せず | ユーザーが`gh label create`で手動作成 |
| 4 | scheduled実行が毎回クラッシュ（orphanブランチとの3点diff） | Issue #232 / PR #233 |
| 5 | `status:queued`が0件で何もdispatchされない | Issue #220の例外的な手動運用が原因と判明、ラベル手動修正で対応 |
| 6 | 本ドキュメントの作成 | Issue #234 |

## 詳細

### 1. `run_state.json`永続化のgit add失敗
状態永続化用ステップの`git add "$RUN_STATE_PATH"`が、リポジトリルートの`.gitignore`（`*.json`）
ルールに引っかかりexit 1していた（`set -e`によりジョブ全体が失敗）。`git add -f`へ変更して解消。

### 2. `dispatcher.py`の`file_lock()`が本体の例外をマスク
`file_lock()`が、ロック取得（`mkdir`/`open`/`flock`）の例外処理と同じ`try`内で`with`body の
`yield`を行っていたため、body側（例: `gh issue edit --add-label`の失敗）で発生した例外が
ロック取得失敗用の`except Exception`に誤って捕捉され、二重`yield`となり
`RuntimeError: generator didn't stop after throw()`という無関係なエラーに化けて本来の原因を
隠していた。ロック取得と本体実行のtry/exceptを分離し解消。

**教訓**: 汎用的な`except Exception`でcontext managerのbodyごと囲むと、本体側の例外処理を
壊すことがある。ロック取得固有の例外処理と、body実行そのものは明確に分離するべき。

### 3. ラベル未作成
`status:external-lock` / `status:done` / `status:blocked-recompute` / `status:force-serial` /
`risk:flagged`のラベルがリポジトリに一度も作成されていなかった。`gh issue edit --add-label`は
未作成のラベルに対して失敗するため、上記2の例外マスクと組み合わさって原因特定を難しくしていた。

**教訓**: dispatcherが使う全ラベルを、パイロット開始前にチェックリスト化して事前作成しておくべき
だった（本ドキュメントの運用マニュアル側に一覧を記載済み）。

### 4. 無関係な履歴を持つブランチ（orphanブランチ）とのdiffでクラッシュ
外部ロック検知（`scan_external_locks`）が、リポジトリ内の全リモートブランチを`origin/main`との
3点diff（`git diff A...B`）で比較する。ところが、状態永続化用に`git checkout --orphan`で作成した
`orchestune-state`ブランチは`main`と共通の祖先を持たないため、3点diffが
`fatal: no merge base`（exit 128）で失敗し、未捕捉のまま`dispatch-cycle`全体をクラッシュさせていた。

これは`orchestune-state`固有の問題ではなく、**mainと無関係な履歴を持つブランチが1つでも
リポジトリにあれば同様に発生する**、`github.branch_changed_files`の汎用的な頑健性の欠如だった。
既存の`check_footprint_deviation`と同じパターン（gitエラーを握りつぶし空リストを返す）に統一して解消。

**教訓**: 外部ブランチスキャン系のgit操作は、想定外のブランチ形状（orphan・shallow・削除済み等）に
対して常に「エラー時は安全側にスキップ」で書くべき。1箇所だけ例外処理が漏れていた。

### 5. 例外的な手動dispatch（Issue #220）による依存解決の停止
パイロット中、Issue #220（`editor-design-tokens`、5つの後続サブタスクの依存先）を
dispatcher経由ではなくAgent側で例外的に直接ルーチン登録して進めていた。作業完了後、人間が
Issueを直接Closeしたが、dispatcherの自動遷移（`status:in-progress`→`status:done`のラベル付け替え）
を経由していなかったため、ラベルは`status:in-progress`・`status:external-lock`のまま残った。

さらに、`list_issues_by_label`は`--state open`のIssueしか見ないため、後から`status:done`を
付けても（Issueがcloseされている限り）依存解決判定（`_promote_blocked_tasks`）から見えない。
結果として、後続5サブタスク（#221〜#225）は`status:blocked`のまま永久に昇格せず、
かつ大元の`review-history-backend-service`（#217）にも一度も`status:queued`が付与されて
いなかったため、パイロット全体で`status:queued`のIssueが0件という状態になっていた。

対応: #220を再オープンし、ラベルを`status:done`に付け替え。#217に`status:queued`を追加。

**教訓（今回の意思決定）**: コード側を頑健化する（closeされたIssueも`status:done`判定に含める等）
選択肢もあったが、今回は見送り、**「dispatcher管理下のIssueには、queued登録後は人間が直接
ラベル変更・close操作をしない」という運用ルールで回避する**ことにした。理由は、根本原因が
仕様の未把握（そもそも黄金経路から外れた操作をしてしまったこと）にあり、コードの頑健化よりも
先に運用ルールの徹底が優先度が高いと判断したため。コード側の頑健化は、今後同種の逸脱が
繰り返し発生するようであれば再検討する。
