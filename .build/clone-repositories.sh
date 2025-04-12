#!/bin/bash

# 引数でリポジトリリストのファイル名が指定されているか確認
if [ -z "$1" ]; then
    REPO_FILE="repositories.txt"
else
    REPO_FILE=$1
fi

# カレントディレクトリのパスを取得
CURRENT_DIR=$(pwd)

# リポジトリリストのファイルのパスを設定
REPO_FILE_PATH="${CURRENT_DIR}/${REPO_FILE}"

# ファイルが存在するか確認
if [ ! -f "$REPO_FILE_PATH" ]; then
    echo "ファイル $REPO_FILE_PATH が存在しません。"
    exit 1
fi

# リポジトリをクローンまたは更新する関数
update_repository() {
    local REPO_URL=$1
    local BRANCH=${2:-main}

    # 引数が空白の場合は終了
    if [ -z "$REPO_URL" ]; then
        echo "GitリポジトリのURLが提供されていません"
        return 1
    fi

    # リポジトリ名部分を抽出
    REPO_NAME=$(basename "$REPO_URL" .git)

    # 拡張子を削除してリポジトリ名を取得
    REPO_NAME="${REPO_NAME%.*}"
    echo "リポジトリ名: $REPO_NAME"

    # クローンするディレクトリのパス（カレントディレクトリの直下）
    CLONE_PATH="${CURRENT_DIR}/${REPO_NAME}"

    # gitがインストールされていることを確認
    if ! command -v git &> /dev/null; then
        echo "gitが見つかりませんでした"
        return 1
    fi

    echo $REPO_URL

    # リポジトリが存在するか確認
    if git ls-remote "$REPO_URL" > /dev/null 2>&1; then
        # ディレクトリが存在するか確認し、存在しなければクローン、存在すればプルする
        if [ ! -d "$CLONE_PATH/.git" ]; then
            echo "リポジトリをクローンしています..."
            git clone -b "$BRANCH" "$REPO_URL" "$CLONE_PATH"
            if [ $? -eq 0 ]; then
                echo "リポジトリのクローンに成功しました"
            else
                echo "リポジトリのクローンに失敗しました"
                return 1
            fi
        else
            echo "リポジトリは既に存在します。更新しています..."
            cd "$CLONE_PATH"
            git pull origin "$BRANCH"
            if [ $? -eq 0 ]; then
                echo "リポジトリの更新に成功しました"
            else
                echo "リポジトリの更新に失敗しました"
                return 1
            fi
        fi

        # .buildフォルダ内のclone-repositories.shを実行
        if [ -f "${CLONE_PATH}/.build/clone-repositories.sh" ]; then
            echo ".buildフォルダ内のclone-repositories.shを実行しています..."
            cd "${CLONE_PATH}"
            bash .build/clone-repositories.sh .build/repositories.txt
            cd "../"
        fi
    else
        echo "リポジトリが存在しません。"
        return 1
    fi
}

# ファイルから一行ずつ読み込み、リポジトリを更新
while IFS= read -r repo_url; do
    update_repository "$repo_url"
done < "$REPO_FILE_PATH"

echo "リポジトリの取得が完了しました！"