---
name: "orchestune-dispatch-draft"
description: "「大きな石」（複数タスクからなる大規模な作業）の分解案生成(dag.py)とディスパッチャー(dispatcher.py)のスケジュール登録を呼び出す、パイロット運用専用のドラフト版導線。"
version: "0.1.0-draft"
category: "Development"
input_schema:
  type: "object"
  properties: {}
output_schema:
  type: "object"
  properties: {}
---

# Orchestune Dispatch Draft Skill (ドラフト版)

> **これはドラフト版です。** 正式なスキルとしての完成度（`local-ci-developer`スキルと同水準の作り込み）は目指しておらず、
> Issue #181のパイロット運用を実行可能にすることだけを目的とした最小限の導線です。
> パイロット運用で得られた知見（DAG推定精度・クオータ消費・コンフリクト有無）を反映し、
> `skill-creator`スキルを用いて本格版スキルへ更新される予定です（Issue #181のToDo参照）。
> ステージ2.2（ブランチスタッキング, #185）・ステージ3（統合コーディネーター, #186）は未実装であり、
> 本ドラフトのパイロット対象外です。

## トリガー条件

**人間が複数タスクからなる「大きな石」を提示し、並列実装したいと述べた場合**にロードする。

## 前提

- `tools/orchestune/`（独立Poetry環境）に `src/dag.py`（分解案パース・DAG構築、#183）と
  `src/dispatcher.py`（クオータ管理・優先度選出・外部排他制御・worktree起動、#184）が実装済みであること。
- ディスパッチャーの書き込み系操作（ラベル更新・`git worktree`作成・エージェント起動）は、
  **既定で実行される**（`--apply`が既定`True`）。dry-run確認したい場合は`--no-apply`を
  明示指定する（#328でapplyを既定に変更。動作確認したい場合は必ず`--no-apply`結果を
  人間が確認してから実運用すること）。
- `dispatcher.py`のエージェント実起動先は`DispatcherConfig.dispatch_target`
  （`src/dispatch_targets.py`の`DispatchTarget`を実装したクラス）で切り替え可能である（#215）。
  既定は`LocalProcessDispatchTarget`（ローカルsubprocessを起動。`command_builder`未指定時は
  ダミー実装`default_dry_run_command_builder`が`["true"]`を返すのみで実際には何もしない）。
  `poetry run dispatch-cycle --apply --dispatch-target cloud-routine` を指定すると、
  Claude Codeクラウドルーチン（[claude.ai/code/routines](https://claude.ai/code/routines)で
  事前にAPIトリガー付きルーチンを作成しておく必要がある）の`/fire` APIへ実ディスパッチする
  `ClaudeCodeCloudRoutineDispatchTarget`が使われる。ルーチンID・トークンは
  `--routine-id`/`--routine-token`、または`ORCHESTUNE_ROUTINE_ID`/`ORCHESTUNE_ROUTINE_TOKEN`
  環境変数で渡す（未設定の場合は警告を出した上でローカルのダミー動作へ自動フォールバックする）。
  クラウドルーチンの完了判定は、セッション状態のポーリングAPIが現時点で公開されていないため、
  対象ブランチにオープンなPRが立ったことをプロキシシグナルとして使う（既知の暫定仕様）。
  別の起動方式に差し替えたい場合は、`DispatchTarget`を実装した新しいクラスを
  `DispatcherConfig(dispatch_target=...)`に注入するだけでよい。

## ステージ1呼び出し手順（分解案生成）

1. 人間から受けた「大きな石」の説明を、サブタスク単位に分解する。各サブタスクについて
   `id` / `description` / `footprint`（想定変更ファイル一覧）/ `symbols`（想定シンボル一覧）/
   `depends_on`（明示的な依存先ID一覧）を洗い出す。
2. `decomposition_plan.md` を作成する。`dag.py`の`parse_decomposition_plan`が期待するYAMLフロントマター形式:

   ```markdown
   ---
   subtasks:
     - id: task-a
       description: "Aを実装する"
       footprint:
         - src/foo.py
       symbols:
         - foo.Foo
       depends_on: []
   ---

   # Decomposition Plan
   （本文は自由記述、パース対象外）
   ```

3. DAGを構築する:

   ```bash
   cd tools/orchestune
   poetry run python -c "
   from src.dag import build_dag_from_plan
   import json
   print(json.dumps(build_dag_from_plan('../../decomposition_plan.md'), ensure_ascii=False, indent=2))
   "
   ```

4. 出力されたトポロジカル順・並列実行可能leaf・`risky_subtask_ids`（リスクフラグ付きサブタスク）を
   人間に提示し、**この分解案のみ**の承認を得る（個別サブタスクごとの承認は不要。Issue #181の
   「人間の承認ゲートを1点に絞る」方針に従う）。
5. 承認後、既存の`local-ci-developer`スキルのワークフローに従い、サブタスクごとにGitHub Issueを起票する。
   Issue本文には、`dispatcher.py`の`parse_task_from_issue`が読み取れるよう、以下の形式で
   footprint/symbols/subtask_id/depends_onを埋め込む（#193: `depends_on`は依存解決による
   `status:blocked` → `status:queued`昇格判定に使われるため、依存先がある場合は必ず記載する）:

   ```markdown
   ## Footprint
   ```yaml
   subtask_id: task-a
   footprint:
     - src/foo.py
   symbols:
     - foo.Foo
   depends_on:
     - task-x
   ```
   ```

   ラベルは `status:queued`（`depends_on`が未解決なら`status:blocked`）、`priority:low|medium|high`、
   リスクフラグ付きなら`risk:flagged`を付与する。

## ステージ2呼び出し手順（ディスパッチャーのスケジュール登録）

1. パイロット運用者が `mcp__Claude_Code_Remote__create_trigger` で定期実行トリガーを実登録する。例:
   - `cron_expression`: `"*/30 * * * *"`（30分毎。実際の分は :00/:30 を避けてずらすこと）
   - `create_new_session_on_fire`: `true`（毎回まっさらなセッションから実行し、クオータ消費を抑える）
   - `prompt`: 「`cd tools/orchestune && poetry run dispatch-cycle` を実行し、選出結果・quota状況・
     external-lock変更・footprint逸脱イベントを人間に要約報告せよ。リスクフラグ付き・quota枯渇の場合は
     その旨を明記せよ。」
2. `dispatch-cycle` は既定でapply（実際にラベル更新・worktree作成・エージェント起動まで行う）である。
   動作確認だけしたい場合は`--no-apply`を指定してdry-run実行し、選出結果・クオータ状況・
   ロック判定のみをJSONで出力させる。
3. 人間がレポートを見て問題ないと判断した場合、以下を実行し実際にdispatchする（`--no-apply`を
   付けなければ既定でapplyされる）:

   ```bash
   cd tools/orchestune
   poetry run dispatch-cycle --dispatch-target cloud-routine
   ```

   （#215）このとき、`--dispatch-target cloud-routine`かつ`ORCHESTUNE_ROUTINE_ID`/
   `ORCHESTUNE_ROUTINE_TOKEN`環境変数（または`--routine-id`/`--routine-token`）が
   設定されていれば、Claude Codeクラウドルーチンの`/fire` APIへ実際にディスパッチされる。
   未設定の場合や`--dispatch-target`を省略した場合は、既定の`LocalProcessDispatchTarget`
   （ダミー実装のままなら実際にはエージェントプロセスは起動せず、worktree作成・ラベル更新・
   `run_state.json`更新のみ行われる）にフォールバックする。

## ステージ2.1: footprint逸脱時の動的ロック要求・DAG再計算（#192, #200）

`dispatch-cycle`は実行中（`status:in-progress`）のworktreeについて、宣言footprintを
超えて変更されたファイルがないかを毎サイクル検知する。逸脱を検知した場合の挙動は以下の通り。

1. **微小逸脱の許容バッファ**（#200）: 変更行数（追加+削除）が`--deviation-buffer-lines`
   （既定5行）以下の逸脱は、ライブロック（チャーン）防止のため無視される。バイナリファイルの
   変更は行数で測れないため、バッファに関わらず常に逸脱として扱われる。
2. **DAG再計算・通知**（#192）: バッファを超える逸脱を検知すると、GitHub Issue
   （`status:queued` / `status:in-progress` / `status:external-lock`）から動的にサブタスク群を
   再構築し、`dag.recompute_dag_for_footprint_change`でDAGを再計算する。新たな結合度衝突
   （`FootprintConflict`）が見つかった場合、`notify_recompute`が発覚サブタスク・競合相手・
   親Issueへコメントを投稿し、ブロックされるサブタスクに`status:blocked-recompute`ラベルを
   付与する。**この記録は省略不可の手順である**（分解プロンプトの改善サイクルを回すため）。
3. **リトライ上限と強制直列化フォールバック**（#200）: 同一サブタスクの逸脱によるDAG再計算が
   `--max-recompute-retries`（既定2回）を超えて発生した場合、それ以上の再計算・通知は行わず
   （タスク間の「お互いに退避し合う」ライブロックを防ぐため）、そのサブタスクに
   `status:force-serial`ラベルを付与し親Issueへ通知した上で、**新規タスクのdispatchを
   このサブタスクが完了するまで凍結する**（`quota_slots_available`は0として報告される）。
   一度強制直列化されたサブタスクは、以後の逸脱検知でも再計算・通知を行わない
   （`deviation_events`に`action: "already_forced_serial"`として記録されるのみ）。
4. dry-run時（`--no-apply`指定時）は、上記のコメント投稿・ラベル付与は一切行われず、
   `deviation_events`にどのアクションが実行される見込みかのみが記録される
   （`recompute_count`・`forced_serial`の状態も永続化されない）。

## タスク完了検知・クオータ解放・依存解決（#193）

`dispatch-cycle`は毎サイクル冒頭で、`status:in-progress`のactive worktreeについて
完了を判定する。判定方法は起動時に使った`dispatch_target`によって異なる（#215）。
以前は一度dispatchしたタスクが`run_state.active_worktrees`に残り続けクオータが
恒久的に枯渇していた問題（同一cycle内でクオータが解放され新規タスクが選出される）が解消されている。

1. **完了判定**:
   - `LocalProcessDispatchTarget`（既定）: 記録済み`pid`のプロセス生存確認
     （`os.kill(pid, 0)`）により完了を判定する。ダミー`command_builder`（`["true"]`）は
     ほぼ即座に終了するため、実エージェントが未接続の状態でも次サイクルで即完了扱いになる点に注意する。
   - `ClaudeCodeCloudRoutineDispatchTarget`: 対象ブランチにオープンなPRが立った時点で
     完了とみなす（セッション状態のポーリングAPIが無いための暫定的なプロキシシグナル）。
2. **未コミット変更が残る場合は安全側でスキップ**: `git status --porcelain`で
   worktreeに未コミットの変更が検知された場合、**worktree削除・ラベル遷移は行わず**
   （`completion_events`に`action: "completion_skipped_dirty_worktree"`として記録）、
   人間の確認を待つ。作業内容を自動では失わせない設計判断である。
3. **クリーンな場合の後処理**: `git worktree remove`（`--force`は使わない）で
   worktreeを撤去し、`run_state.active_worktrees`から除去してクオータを解放、
   ラベルを`status:in-progress` → `status:done`へ遷移する。
4. **依存解決による昇格**: `status:blocked`のサブタスクについて、`depends_on`に
   列挙された全サブタスクIDが`status:done`（または当サイクルで完了したもの）に
   含まれていれば、`status:blocked` → `status:queued`へ自動昇格する
   （`promotion_events`に記録）。昇格したタスク自体は次サイクル以降で選出対象になる。
5. dry-run時（`--no-apply`指定時）は上記の`git worktree remove`・ラベル遷移は一切行われず、
   `completion_events`・`promotion_events`にプレビューのみが記録される。

## リモートブランチの自己ロック誤検知修正（#194）

外部作業スキャン（ステージ2.3）で`git branch -r`由来のブランチ名
（`origin/`プレフィックス付き）をPRの`headRefName`・ディスパッチャ自身のブランチ名
と正規化してから突き合わせるよう修正済み。以前はこの正規化が欠けていたため、
ディスパッチャが自分自身の起動ブランチを「外部の変更」と誤認し、footprintが
重複するqueuedタスクを誤って`status:external-lock`にし得た。

## #183・#184完了後の疎通確認チェックリスト

- [ ] `decomposition_plan.md`のサンプルを1件作成し、上記ステージ1手順3で`build_dag_from_plan`が
      例外なくJSONを返すことを確認した
- [ ] `poetry run dispatch-cycle --no-apply`（dry-run、`--run-state-path`等はテスト用一時ディレクトリを指定）が
      実際のGitHub Issue（またはモックした`gh`コマンド）に対して例外なくJSONレポートを出力することを確認した
- [ ] `poetry run dispatch-cycle`（既定でapply）を隔離環境で1回実行し、`git worktree`が実際に作成され、
      `run_state.json`が正しく更新されることを確認した
- [ ] パイロット運用でこのドラフト導線を実際に使用した
