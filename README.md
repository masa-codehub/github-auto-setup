# github-auto-setup

## GitHub Personal Access Token (PAT) の準備
このツールを使用するには、GitHub Personal Access Token (PAT) が必要です。PATには以下のスコープを付与してください:
- `repo`: プライベートリポジトリへのアクセス、Issue作成、ラベル作成などに必要です。
- `project`: GitHub Projects (V2) へのIssue追加に必要です。

取得したPATは、環境変数 `GITHUB_PAT` に設定してください。

## 技術スタック

本プロジェクトで使用されている主要な技術スタックは以下の通りです。

* **Webフレームワーク:** Django
* **フロントエンド:** Bootstrap 5, JavaScript (最小限)
* **CLIフレームワーク:** Typer
* **AI連携:** LangChain, OpenAI API, Google Gemini API
* **GitHub APIクライアント:** githubkit
* **設定管理:** Pydantic Settings, YAML
* **コンテナ技術:** Docker
* **コアロジック言語:** Python

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

## ツールの使用方法 (Web UI)

### 画面レイアウト

- **ウェルカムメッセージ**: ページ上部に全幅で表示されます。
- **左カラム**: ファイルアップロード、Issue一覧（アコーディオン形式で詳細表示）、情報カードが縦に並びます。
- **右カラム**: アクションパネル（上部に主要操作、下部にAI設定UI）が表示されます。

### Issue一覧と詳細表示

- Issue一覧は左カラムに表示されます。
- 各Issue行をクリックすると、アコーディオン形式で本文などの詳細情報が展開されます。
- チェックボックス操作とアコーディオン展開は独立して動作します。

### AI設定UI

- アクションパネル下部に「AI設定」セクションがあります。
- AIプロバイダー（OpenAI/Gemini）をラジオボタンで選択できます。
- 選択したプロバイダーに応じて、対応するモデル名をドロップダウンから選択できます。
    - OpenAI: gpt-4o (Default), gpt-4, gpt-3.5-turbo
    - Gemini: gemini-1.5-pro (Default), gemini-pro
- APIキーは1つの入力欄で管理します。
- 現時点では各ボタンやフォームはダミーで、バックエンド連携や動的制御は未実装です。

### スタイルと動作

- Bootstrap 5 によるレスポンシブなレイアウトです。
- レイアウト崩れや主要UI要素の欠落がないことを確認してください。

このツールは、Issue情報ファイルからGitHubリソースを一括で作成・管理するためのWebインターフェースを提供します。
主な操作は以下の3つのステップで行います。

### ステップ1: Issue情報ファイルのアップロード

1.  **ファイル選択:**
    * ページ上部のウェルカムメッセージの下、画面左側の「**1. Upload Issue File**」セクションにあるファイル選択ボタン（`<input type="file" id="issue-file-input">`）をクリックします。
    * ダイアログから、Issue情報が記述されたファイル（Markdown, YAML, または JSON形式）を選択します。
2.  **アップロードとプレビュー:**
    * ファイルを選択後、「**Upload & Preview**」ボタン (`<button id="upload-button">`) をクリックします。
    * ファイルの内容が解析され、結果が次の「Issue一覧表示エリア」に表示されます。
    * エラーが発生した場合は、ページ上部の通知エリア (`<div id="result-notification-area">`) にメッセージが表示されます。

### ステップ2: Issueのプレビューと選択

1.  **内容確認:**
    * 左カラムの「**2. Preview & Select Issues**」セクションのテーブル (`<table id="issue-table">`) に、アップロードされたファイルから読み込まれたIssueの一覧が表示されます。
    * 各Issueの「Title」、「Assignees」、「Labels」などが確認できます。
    * 読み込まれたIssueの件数が「Found X issues.」のように表示されます (`<p id="issue-count-indicator">`)。
2.  **Issue選択:**
    * GitHubに登録したい、またはローカルに保存したいIssueの行の左端にあるチェックボックス (`<input type="checkbox" class="issue-checkbox">`) をオンにします。
    * テーブルヘッダーのチェックボックス (`<input type="checkbox" id="select-all-header-checkbox">`) を使うと、一覧に表示されている全てのIssueを一括で選択/解除できます。
    * 個別に選択を制御したい場合は、「**Select All**」ボタン (`<button id="select-all-button">`) および「**Deselect All**」ボタン (`<button id="deselect-all-button">`) も利用できます。

### ステップ3: アクションの実行

画面右側の「**3. Execute Actions**」パネル (`<div id="action-panel-section">`) で、選択したIssueに対する操作を行います。

#### GitHubへのIssue登録

1.  **リポジトリ名入力:**
    * 「**Repository**」入力フィールド (`<input type="text" id="repo-name-input">`) に、Issueを登録したいGitHubリポジトリ名を `owner/repository` の形式で入力します（例: `your-username/my-project`）。
2.  **プロジェクト名入力 (任意):**
    * Issueを特定のGitHubプロジェクト（Projects V2）に関連付けたい場合は、「**Project Name**」入力フィールド (`<input type="text" id="project-name-input">`) にプロジェクト名を入力します。
3.  **Dry Runモード選択:**
    * 「**Dry Run Mode**」スイッチ (`<input type="checkbox" id="dry-run-checkbox">`) をオン（デフォルト）にすると、実際にはGitHubにIssueを作成せず、どのようなIssueが作成されるかのシミュレーション（ログ出力など）のみを行います。実際にIssueを作成する場合は、このスイッチをオフにしてください。
4.  **登録実行:**
    * 「**Create Issues on GitHub**」ボタン (`<button id="github-submit-button">`) をクリックします。
    * 処理結果はページ上部の通知エリアに表示されます。

#### ローカルへのIssue保存

1.  **保存先ディレクトリ入力 (任意):**
    * 「**Save Directory**」入力フィールド (`<input type="text" id="local-path-input">`) に、Issue情報をファイルとして保存したいローカルマシンのディレクトリパスを入力します。省略した場合は、デフォルトのパス（例: `./output_issues`）に保存されます。
2.  **保存実行:**
    * 「**Save Issues Locally**」ボタン (`<button id="local-save-button">`) をクリックします。
    * 処理結果はページ上部の通知エリアに表示されます。

## GitHub PAT接続テストスクリプトの利用方法

プロジェクトルートで以下のコマンドを実行してください:

```bash
python -m scripts.test_github_connection
```

- 必要な環境変数 `GITHUB_PAT` を事前に設定してください。
- PATには `repo` および `project` スコープが必要です。
- スコープ不足や認証エラー時はエラーメッセージとともに終了コード1で終了します。
- スクリプトは `githubkit` パッケージに依存します。

---