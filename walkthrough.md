# Walkthrough: 「再執筆」ボタンへの確認モーダル追加

本PRでは、Editor画面の各話カードにある「🔄 再執筆」ボタンに、実行前の確認モーダルを追加しました（[Issue #136](https://github.com/Saltmu/manuscriptune/issues/136)）。

## 背景

- 既存の指摘反映ボタン（「反映を実行」）には確認モーダル（`showApplyModal`）があるが、「再執筆」ボタンには確認処理が一切なく、クリック直後に `runWriteForEpisode(ep.title)` が実行され、AIによる本文の再生成（上書き）が即座に開始されていた。
- バックエンド（`src/routes/novels.py` の `stream_write`）は再執筆前に既存ファイルを `reviews/{basename}/history/v{n}/` へ自動退避するため完全なデータ消失は起きないが、UI上にその安全性が示されておらず、誤クリックによる無駄なAPIコスト・処理時間の発生や、ユーザーの不安を招いていた。

## 変更内容

- **`frontend/src/views/Editor.svelte`**:
  - 新規状態 `showRewriteConfirmModal` / `pendingRewriteEpisode` を追加
  - 「🔄 再執筆」ボタンの `on:click` を、直接 `runWriteForEpisode` を呼ぶ形から `openRewriteConfirm(ep)` を呼ぶ形に変更
  - 既存の `showApplyModal` と統一感のあるスタイルの確認モーダルを追加。対象話名、現在の本文が履歴に自動退避されたうえで置き換えられる旨を明記し、「キャンセル」「再執筆を実行」ボタンを配置
  - 未執筆エピソードの「✍️ 執筆する」ボタン（上書き対象が存在しない）は変更なし

バックエンド（API・データモデル）への変更はありません。

## 検証結果

### ブラウザでの手動検証
`poetry run server`（バックエンド）と `npm run dev`（フロントエンド）を起動し、実データで以下を確認しました：
1. 執筆済み/レビュー済みの話で「🔄 再執筆」をクリック → 確認モーダルが表示され、`/api/stream/write` は呼ばれないこと
2. 「キャンセル」をクリック → モーダルが閉じ、APIが呼ばれないこと
3. 「再執筆を実行」をクリック → `/api/stream/write?episode=...` が正しいパラメータで呼び出され、従来通りAI再執筆が開始されること（バックエンドログで `history/v{n}/` への自動退避も確認）
4. コードレビューにより、未執筆の「✍️ 執筆する」ボタンの挙動が変更されていないことを確認

検証で生成された一時的な履歴退避ファイル（`reviews/1_1/history/v2/`、`.gitignore` 対象）はテスト後に削除済みです。

### ローカルCI検証結果
本フロントエンド（Svelte + Vite）にはユニットテスト基盤が存在せず、`./scripts/local-ci.sh` はPython（ruff/mypy/pytest/detect-bloat）のみを検証対象とするため、TDDの対象外としました。バックエンドは変更していませんが、影響がないことを確認するため実行しました。

`./scripts/local-ci.sh` を実行し、以下の項目がすべてパスしたことを確認しました：
- `ruff format`: パス
- `ruff check`: パス
- `mypy`: パス（Success: no issues found in 83 source files）
- `pytest`: パス（229 tests passed, 全体カバレッジ 84.31% で基準 75% をクリア）
- `detect-bloat`: パス
