## システムコンテキスト: github-auto-setup

### 1. 概要と目的

「github-auto-setup」は、ソフトウェア開発プロジェクトにおけるGitHubリソース（特にIssue）の初期セットアップ作業を効率化するためのツールです。 開発者が多様な形式（Markdown, YAML, JSON）のIssue情報ファイルから、手作業を介さずにGitHub上にIssue、ラベル、マイルストーン等を一括で登録・設定できるように支援し、プロジェクトの立ち上げを迅速化することを主な目的とします。

### 2. システム境界と主要な外部要素

* **ユーザー (開発者):** Web UIまたはCLIを通じてシステムと対話します。Issue情報ファイルを提供し、GitHubへの登録指示やローカル保存指示を行います。
* **GitHub API:** システムがリポジトリ、Issue、ラベル、マイルストーン、プロジェクトアイテムを作成・確認するために利用する主要な外部インターフェースです。PAT (Personal Access Token) による認証が必要です。
* **AIサービス (OpenAI/Gemini API):** アップロードされたファイル内容を解釈し、構造化されたIssueデータ（`IssueData`モデル）にマッピングするために利用されます。APIキーが必要です。
* **ローカルファイルシステム:** ユーザーがアップロードするIssue情報ファイルの読み込み元であり、オプションで処理後のIssue情報を個別のYAMLファイルとして保存する先となります。
* **設定ファイル (`config.yaml`):** AIモデル名、プロンプトテンプレート、ログレベルなどのアプリケーション動作をカスタマイズするための設定情報を提供します。
* **環境変数:** GitHub PAT、AI APIキー、AIモデルタイプなど、主に秘匿情報や実行環境に依存する設定を提供します。設定ファイルより優先されます。

### 3. 主要な機能とスコープ

本システムは、以下の主要機能を提供します。

* **入力処理:**
    * Markdown, YAML, JSON形式の単一Issue情報ファイルの受け付け（Web UIからのアップロード、またはCLIからのパス指定）。
    * ファイル形式に応じた初期パーサー（`MarkdownIssueParser`, `YamlIssueParser`, `JsonIssueParser`）によるIssueブロックへの分割。
    * `AIParser`を用いた、Issueブロックから構造化データモデル`ParsedSourceFileContent`（内部に`IssueData`リストおよびファイル全体のメタ情報を含む）への解釈・マッピング。キーの揺らぎ吸収も担う。
* **Web UI機能:**
    * **HTML, CSS, JavaScript（最小限）およびBootstrap 5で構築された静的Web UI。**
    * アップロードされたファイルのIssue一覧プレビューと詳細表示（アコーディオン）。
    * 処理対象Issueの選択（個別、一括）。
    * GitHub登録アクション（リポジトリ名、プロジェクト名指定、Dry Runモード）。
    * ローカルファイル保存アクション（保存先ディレクトリ指定）。
    * AIプロバイダーおよびモデル選択、APIキー入力。
* **CLI機能:**
    * Web UIと同等のコアなGitHubリソース作成機能（ファイルパス、リポジトリ名、プロジェクト名、Dry Runモードなどを引数で指定）。
* **GitHubリソース作成 (コアロジック):**
    * リポジトリの作成（存在しない場合）または既存リポジトリの利用。
    * ラベルの作成（存在しない場合）。
    * マイルストーンの作成（存在しない場合）。
    * 担当者の有効性検証（GitHub API経由）。
    * 選択されたIssueのGitHub Issueとしての作成（タイトル、本文、ラベル、マイルストーン、検証済み担当者の設定）。
    * 作成されたIssueのGitHub Projects (V2) への追加（任意）。
    * Dry Runモードのサポート。
* **ローカルファイル保存:** 解析・マッピングされたIssue情報を、個別のYAMLファイルとしてローカルに保存し、目次となる`index.html`を生成。

**スコープ外:**

* GitHub上のIssueやリポジトリの状態を読み取り、ローカルのIssue定義ファイルと双方向で同期する機能。
* Issueの更新機能（現在は新規作成を優先）。
* Markdownファイル自体の生成・編集支援。
* Pull Requestの自動作成や連携。
* GitHub以外のプラットフォーム連携 (Jira, GitLab等)。
* **Web UIにおけるモダンなJavaScriptフレームワーク（React, Vueなど）の利用。**

### 4. システム構造とコンポーネント

* **プレゼンテーション層:**
    * **Web UI (静的HTML/CSS/JS):** **ユーザーとのインタラクションを担当する静的なHTML/CSS/JavaScriptファイル群。Bootstrap 5を利用。Djangoはこれらの静的ファイルをホスティングし、APIリクエストを処理する。**
    * **CLI (`webapp/core_logic/github_automation_tool/main.py`):** Typer を使用したコマンドラインインターフェース。
* **アプリケーションサービス層 (検討中):**
    * Django アプリケーション内にサービス層（例: `webapp/app/services.py`）を設け、UIからのAPIリクエストをビジネスロジック（UseCase）に橋渡しする役割。設定情報の管理やUseCaseの呼び出し調整などを担当。
* **ドメイン/ユースケース層 (`webapp/core_logic/github_automation_tool/`):**
    * **Use Cases:** アプリケーションのコアなビジネスフローを実装 (`CreateGitHubResourcesUseCase`, `CreateIssuesUseCase`, `CreateRepositoryUseCase`など)。
    * **Domain Models:** システムの中核となるデータ構造とバリデーションルールを定義 (`IssueData`, `ParsedSourceFileContent`, `CreateIssuesResult`など)。
    * **Domain Exceptions:** ビジネスルール違反や処理中の特有なエラーを示す例外クラス。
* **アダプター層 (`webapp/core_logic/github_automation_tool/adapters/`):**
    * **File Parsers:** 各種入力ファイル形式の初期解析（`MarkdownIssueParser`, `YamlIssueParser`, `JsonIssueParser`）。
    * **AI Parser:** LangChainとAIモデル（OpenAI/Gemini）を利用し、Issue情報を構造化データへマッピング。
    * **GitHub Clients:** `GitHubRestClient`（REST API用）, `GitHubGraphQLClient`（GraphQL API用）を提供。
    * **Assignee Validator:** GitHub担当者の有効性を検証。
    * **CLI Reporter:** CLI向けの処理結果出力。
* **インフラストラクチャ層 (`webapp/core_logic/github_automation_tool/infrastructure/`):**
    * **Config:** 設定ファイル (`config.yaml`) と環境変数からの設定情報読み込みと管理。
    * **File Reader:** ローカルファイルシステムからのファイル読み込み。

### 5. データモデル `ParsedSourceFileContent` の役割

* **目的:** 単一の入力ファイル（例: `requirements.md`, `project_tasks.yaml`）から、初期パーサーとAIパーサーによって解析・抽出された全ての情報を集約して保持するためのデータモデルです。
* **主な内容:**
    * `issues: List[IssueData]`: ファイルから抽出された個々のIssue情報（`IssueData`オブジェクトのリスト）。これは、AIパーサーがファイル内の各Issueブロックを解釈し、構造化した結果です。
    * **ファイル全体のメタ情報 (検討中・提案):**
        * 例: `default_project_name: Optional[str]` (ファイル全体で示唆されるデフォルトのGitHubプロジェクト名)
        * 例: `suggested_labels: List[str]` (ファイル全体で共通して提案されるラベル群)
        * 例: `suggested_milestones: List[str]` (ファイル全体で共通して提案されるマイルストーン群)
        これらのメタ情報は、ファイル全体を俯瞰してAIが抽出するか、あるいはファイルの特定のセクション（例: YAMLのトップレベルキー）から読み込むことが想定されます。この情報は、後続のGitHubリソース作成時にデフォルト値として利用されたり、ユーザーへの提案としてUIに表示されたりする可能性があります。

このデータモデルは、ファイル読み込み・解析処理の最終的な出力であり、後続のGitHubリソース作成UseCase (`CreateGitHubResourcesUseCase`) やローカル保存機能への主要な入力となります。

### 6. インターフェース間の機能分担

* **システム全体で提供するコア機能:**
    1.  指定されたファイルパスからIssue情報ファイルを読み込む機能。
    2.  読み込んだファイル内容をファイル形式に応じて初期解析し、Issueブロック群に分割する機能。
    3.  Issueブロック群と（必要であれば）ファイル全体のコンテキストをAIに渡し、構造化された`ParsedSourceFileContent`（主に`List[IssueData]`とメタ情報）を生成する機能。
    4.  `ParsedSourceFileContent`とユーザー指示（リポジトリ名、プロジェクト名、DryRunなど）に基づき、GitHubリソース（リポジトリ、ラベル、マイルストーン、Issue、プロジェクト連携）を作成・設定する機能。
    5.  `ParsedSourceFileContent`に基づき、Issue情報をローカルファイルシステムにYAML形式で分割保存する機能。
* **Web UIが提供する機能（上記コア機能の利用 + UI固有機能）:**
    * **静的HTMLページからのファイルアップロードインターフェース。**
    * 解析結果（Issueリスト、メタ情報）のインタラクティブなプレビューと詳細表示。
    * 処理対象Issueの視覚的な選択（個別、一括）。
    * GitHub登録情報（リポジトリ名、プロジェクト名、DryRun）のフォーム入力。
    * AI設定（プロバイダー、モデル、APIキー）のUI。
    * ローカル保存先ディレクトリ指定UI。
    * 処理結果の動的なフィードバック表示。
    * **（将来的に）GitHub Pagesなどの静的サイトホスティングサービスからのAPI呼び出しに対応。**
* **CLIが提供する機能（上記コア機能の利用 + CLI固有機能）:**
    * コマンドライン引数によるファイルパス、リポジトリ名、プロジェクト名、DryRunなどの指定。
    * （将来的に）設定ファイルや環境変数を通じたAIパラメータの指定。
    * 処理結果のコンソールへの出力（`CliReporter`経由）。
    * バッチ処理やスクリプトへの組み込みに適したインターフェース。
