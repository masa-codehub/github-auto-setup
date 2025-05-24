# github-auto-setup

## ローカル開発環境での実行と確認

本アプリケーションはDockerコンテナでの実行が推奨されます。

1. **Docker Desktop** がインストールされ、実行中であることを確認してください。
2. リポジトリのルートディレクトリで、ターミナルから以下のコマンドを実行してコンテナをビルドし、起動します:
   ```bash
   docker-compose -f .build/context/docker-compose.yml up --build -d
   ```
   (`-d` はバックグラウンド実行オプションです。ログを確認したい場合は `-d` を外してください。)
3. コンテナの起動ログにエラーがないことを確認します。Django開発サーバーが `0.0.0.0:8000` でリッスンしている旨のメッセージが表示されます。
   ```
   # 例:
   # github-auto-setup_1  | Starting development server at http://0.0.0.0:8000/
   # github-auto-setup_1  | Quit the server with CONTROL-C.
   ```
4. ウェブブラウザを開き、アドレスバーに `http://localhost:8000/` と入力してアクセスします。
5. 「GitHub Automation Tool へようこそ！」という見出しのトップページが表示され、Bootstrap5のスタイル（フォント、ボタンデザイン、カードレイアウトなど）が適用されていることを目視で確認してください。
6. 開発を終了する際は、ターミナルから以下のコマンドでコンテナを停止・削除できます:
   ```bash
   docker-compose -f .build/context/docker-compose.yml down
   ```

### VSCode Devcontainerでの起動

VSCodeの「Reopen in Container」機能を利用して開発コンテナを起動する場合も、上記と同様に `http://localhost:8000/` でトップページを確認できます。

**トラブルシューティング:**
* ポート8000が既に使用されている場合、`.build/context/docker-compose.yml` の `ports` 設定を変更する必要があるかもしれません。
* ビルドや起動でエラーが発生した場合は、DockerのログやDjangoの起動ログを確認してください。