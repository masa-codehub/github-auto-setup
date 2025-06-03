#!/bin/sh

# githubのリポジトリのクローン
bash .build/clone-repositories.sh .build/repositories.txt

# Djangoサーバーの起動 (開発用)
cd webapp
python manage.py runserver 0.0.0.0:8000 &

# ファイルの存在を確認
if [ -f "main.py" ]; then
    echo "main process start"
    python "main.py"
fi
echo "main process done"

wait # バックグラウンドプロセスが終了するまで待機
