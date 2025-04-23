#!/bin/bash
set -e

# これはサンプルプロジェクトのセットアップを行うためのスクリプトです。
# 事前に以下のコマンドを実行して、必要なツールをインストールしてください。
# pip install .  # もしくは poetry install など

# 引数の数をチェック
if [ "$#" -ne 2 ]; then
    echo "使い方: $0 <owner>/<リポジトリ名> "<プロジェクト名>""
    exit 1
fi

REPO_NAME=$1
PROJECT_NAME=$2

gh-auto-tool --file sample_project_setup.md --repo "$REPO_NAME" --project "$PROJECT_NAME"