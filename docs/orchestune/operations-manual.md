# Orchestune 運用マニュアル

`tools/orchestune`（マルチエージェント実装オーケストレーション）を、GitHub Actions経由での
定期dispatch運用も含めて安全に回すための実務マニュアル。設計思想・API仕様は
`skills/orchestune-dispatch-draft/SKILL.md`を参照し、本ドキュメントは日々の運用手順・
ラベル状態の見方・トラブルシューティングに特化する。

## 全体像

1. **Stage 1（分解案生成・承認・Issue起票）**: 人間が提示した「大きな石」をサブタスクに分解し、
   `dag.py`でDAGを構築、人間が分解案を承認した後、サブタスクごとにGitHub Issueを起票する。
2. **Stage 2（ディスパッチ）**: GitHub Actions（`.github/workflows/orchestune-dispatch.yml`）が
   毎時17分に`dispatch-cycle --apply --dispatch-target cloud-routine`を実行し、
   `status:queued`のIssueをClaude Codeクラウドルーチンへ実際にdispatchする。

## ラベルの意味と状態遷移

| ラベル | 意味 |
| --- | --- |
| `status:queued` | dispatch待ちで即時実行可能 |
| `status:blocked` | `depends_on`未解決のため実行不可 |
| `status:in-progress` | dispatch済み・実行中 |
| `status:done` | 完了 |
| `status:external-lock` | 他ブランチ/PRとのfootprint衝突により一時停止中 |
| `status:blocked-recompute` | footprint逸脱によるDAG再計算でブロック中 |
| `status:force-serial` | リトライ上限超過により強制直列化 |
| `risk:flagged` | リスクフラグ付き（要人間確認） |

正常な状態遷移は以下の通り、**すべてdispatcher（GitHub Actions）が自動で行う**。

```
(Issue起票時)
  depends_on解決済み → status:queued
  depends_on未解決   → status:blocked

status:blocked --(依存先がstatus:doneになる)--> status:queued
status:queued  --(dispatch実行)--> status:in-progress
status:in-progress --(完了検知: 対象ブランチにPRオープン)--> status:done
status:queued/in-progress --(他ブランチとのfootprint衝突検知)--> status:external-lock
status:external-lock --(衝突解消)--> status:queued
```

## 運用ルール: dispatcher管理下のIssueに人間が直接触る際の注意

`status:*`ラベルが付いた（＝Orchestuneのパイプラインに乗った）Issueへ人間が直接ラベル変更・
Close操作を行うこと自体は問題ない。ただし以下の1点だけは引き続き注意すること。

- **dispatcher管理外（`run_state.json`の`active_worktrees`に記録されていない）で
  手動dispatchしたIssueは、完了検知（`is_process_alive`/対象ブランチのPRオープン確認）の
  対象にならない**ため、そのままでは`status:in-progress`のまま放置される。手動dispatchした
  タスクを完了させる場合は、`status:in-progress`/`status:external-lock`等を外し
  `status:done`を付けてから、通常通りCloseしてよい（PRのマージによる`Closes #N`での
  自動Closeも問題ない）。

> **#236で修正済み（旧ルールの補足）**: 以前は「完了Issueを直接Closeすると
> `_promote_blocked_tasks`が`--state open`しか見ないため依存先が永久に昇格しない」という
> 制約があり、「Closeしない」運用ルールで回避していた。現在は`status:done`の検索のみ
> `state="all"`でclosedなIssueも含めて検索するよう修正済みのため、完了Issueを通常通り
> Closeしても依存解決の自動昇格は正しく動作する。

## GitHub Actionsワークフローの設定

`.github/workflows/orchestune-dispatch.yml`

- **トリガー**: `schedule`（毎時17分、`--apply`込みで実dispatch）+ `workflow_dispatch`
  （`apply`入力、既定`false`＝dry-run。動作確認時はこちらを使う）
- **状態永続化**: `run_state.json`（quota・完了検知の状態）は、runnerが使い捨てのため
  専用ブランチ`orchestune-state`にコミットして引き継ぐ。このブランチは`main`と共通の祖先を
  持たないorphanブランチであり、**通常のfeatureブランチとして扱わないこと**（マージ・削除・
  rebase等の対象にしない）。
- **必要なSecrets**（リポジトリ管理者が事前に登録）:
  - `ORCHESTUNE_ROUTINE_ID` / `ORCHESTUNE_ROUTINE_TOKEN`:
    [claude.ai/code/routines](https://claude.ai/code/routines)でAPIトリガー付きルーチンを
    作成し、発行されたIDとトークンを登録する。

## 動作確認・トラブルシューティング

- **まず`workflow_dispatch`（`apply: false`）でdry-run実行し、`selected`/`quota_slots_available`/
  `lock_changes`等のJSON出力を確認する。**
- **`status:queued`のIssueが0件で何もdispatchされない場合**: バグではなく、単に
  ディスパッチ待ちのタスクが無いだけの可能性が高い。Issueのラベル状態を確認すること
  （起票時に`status:queued`/`status:blocked`が正しく付与されているか）。
- **scheduled実行が毎回失敗する場合**: まずGitHub Actionsの実行ログ（失敗ジョブのログ）を確認する。
  `gh`コマンドのエラー（`CalledProcessError`）が出ている場合、対象ラベルがリポジトリに
  実在するか（`gh label create`で作成済みか）を疑う。
- **必要なラベルが存在しない場合**: `gh label create "<label>" --color <hex> --description "<desc>" --repo Saltmu/manuscriptune`
  で作成する。少なくとも上記の状態遷移表に出てくる全ラベルが必要。
- **`status:queued`が付いているのにdispatchされない場合**: `status:external-lock`が同時に
  付いていないか確認する（`status:queued`はロック時に外されないため、この2つは併存し得る）。
  dispatcher管理外で手動dispatchしたIssueは、その成果物（同じfootprintを変更するPR/ブランチ）が
  「外部ブランチとの衝突」として誤検知され、`status:external-lock`が付くことがある
  （タスク自身の完了物を「他人の変更」と誤認するケース）。この場合は、対応するPRをマージ後、
  Issueを完了状態（`status:done`）に更新すればロックも解消される。
