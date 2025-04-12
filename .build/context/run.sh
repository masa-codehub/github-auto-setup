#!/bin/sh

# githubのリポジトリのクローン
bash .build/clone-repositories.sh .build/repositories.txt

# ファイルの存在を確認
if [ -f "main.py" ]; then
    echo "main process start"
    python "main.py"
fi
echo "main process done"
