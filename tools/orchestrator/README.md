# tools/orchestrator

マルチエージェントによる実装オーケストレーション（分解案のパース・結合度スコア算出・依存関係DAG構築）を担う、manuscriptune本体から独立したPythonパッケージです。

本体（リポジトリルート）の Poetry 環境・依存関係とは完全に分離されており、独自の `pyproject.toml` / 仮想環境 / ローカルCIスクリプトを持ちます。これにより本体のソースや依存関係を汚さず、将来的に別リポジトリへ切り出すことも容易になります。

## セットアップ

```bash
cd tools/orchestrator
poetry install
```

## テスト・Lint・型チェックの実行

個別に実行する場合:

```bash
cd tools/orchestrator

# フォーマットチェック
poetry run ruff format --check

# Lint
poetry run ruff check

# 型チェック
poetry run mypy src tests

# テスト（カバレッジ計測込み）
poetry run pytest --cov=src --cov-fail-under=75
```

## ローカルCIの一括実行

```bash
./tools/orchestrator/scripts/local-ci.sh
```

以下の順序でチェックを行い、すべて成功した場合のみ正常終了（Exit Code 0）します。

1. Ruff Format (`ruff format --check`)
2. Ruff Lint (`ruff check`)
3. Mypy Type Check (`mypy src tests`)
4. Pytest with Coverage (`pytest --cov=src --cov-fail-under=75`)

カバレッジが75%未満の場合、または上記いずれかのステップが失敗した場合はエラー終了します。

## 本体との関係

- `tools/orchestrator/` は本体のルート `./scripts/local-ci.sh` のテスト・Lintスキャン対象から除外されています（本体側のカバレッジ・Lint結果に影響を与えません）。
- 一方で、ルートの `./scripts/local-ci.sh`（pre-pushフックが呼び出すスクリプト）は、`tools/orchestrator/` 配下に差分がある場合に本スクリプト（`tools/orchestrator/scripts/local-ci.sh`）を自動的に併走させます。これにより、環境を分離しつつも品質ゲートからこのディレクトリが漏れないようになっています。
