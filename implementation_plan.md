# 実装プラン: 「再執筆」ボタンへの確認ダイアログ追加

## 概要
Editor画面の各話カードにある「🔄 再執筆」ボタンをクリックした際、確認モーダルを経由せず即座にAI再生成（本文の上書き）が開始されてしまう問題を修正する。既存の「反映を実行」（指摘反映）と同様の確認モーダルを追加する。

## 背景・目的
- 現状、指摘反映ボタンには確認モーダル（`showApplyModal`）があるが、「再執筆」ボタンには `confirm()` すら無く、`runWriteForEpisode(ep.title)` が直接呼ばれる（[Editor.svelte:532](frontend/src/views/Editor.svelte:532)）。
- バックエンド（[novels.py:290-294](src/routes/novels.py:290)）は再執筆前に既存ファイルを `history/v{n}/` へ自動退避するため、完全なデータ消失は起きない。ただしUI上にその安全性が全く示されておらず、誤クリックで長時間のAI処理とAPIコストが発生し、「本当に戻せるのか」というユーザーの不安・混乱を招く。
- WebUI-Developerスキルのガイドライン（非同期処理・破壊的操作に対する確認）にも反するため、既存の指摘反映モーダルと一貫性を持たせる形で解消する。

## 設計・実装プラン
- 対象ファイル: `frontend/src/views/Editor.svelte`（フロントエンドのみ、バックエンド変更なし）
- 新規リアクティブ変数: `showRewriteConfirmModal`（bool）, `pendingRewriteEpisode`（対象話のタイトル情報）
- 「🔄 再執筆」ボタンの `on:click` を `() => runWriteForEpisode(ep.title)` から `() => openRewriteConfirm(ep)` に変更し、直接実行しないようにする。
- 新規モーダル（既存の `showApplyModal` と同じ見た目・トーン）を追加:
  - 対象話タイトルを明示
  - 「現在の本文は履歴に自動退避されたうえで、AIにより再生成されます」という趣旨の説明文
  - 「キャンセル」「再執筆を実行」ボタン。実行時に `runWriteForEpisode(pendingRewriteEpisode.title)` を呼び出す
- 「✍️ 執筆する」（未執筆エピソードの初回執筆、[Editor.svelte:528](frontend/src/views/Editor.svelte:528)）は上書き対象が存在しないため対象外とする。

## テスト方針
- 本フロントエンド（Svelte + Vite）にはユニットテスト基盤が存在せず、`./scripts/local-ci.sh` もPython（ruff/mypy/pytest/detect-bloat）のみを検証対象としている。バックエンドコードは変更しないため、TDD（pytest）の対象外とする。
- 代わりに `poetry run server` でWebUIを起動し、ブラウザ上で以下を手動検証する:
  1. 執筆済み/レビュー済みの話で「🔄 再執筆」をクリック → 確認モーダルが表示され、AI処理が即座には開始されないこと
  2. 「キャンセル」をクリック → モーダルが閉じ、`/api/stream/write` が呼ばれないこと
  3. 「再執筆を実行」をクリック → 従来通りAI再執筆が開始されること
  4. 未執筆の話の「✍️ 執筆する」は従来通り確認なしで実行されること（挙動不変）
- push前に `./scripts/local-ci.sh` を実行し、既存のPythonテスト・Lint・型チェックに影響がないことを確認する。

## 影響範囲
- `frontend/src/views/Editor.svelte` のみ。API・データモデル・他画面への影響なし。

## オープンな疑問点
- 特になし（スコープを「再執筆ボタンへの確認モーダル追加」に限定した小さな変更）
