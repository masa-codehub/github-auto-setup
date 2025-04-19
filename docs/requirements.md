# 要件定義書: GitHub Automation Tool

**バージョン:** 1.1
**最終更新日:** 2025-04-20
**ステータス:** フェーズ1完了

## 1. 概要と背景

### 1.1. プロジェクトの目的と背景

本プロジェクトは、ソフトウェア開発プロセスにおけるGitHub上のセットアップ作業（リポジトリ作成、Issue登録、ラベル・マイルストーン設定、プロジェクトへのアイテム追加など）の効率化を目的とします。現状、これらの作業、特に要件定義書に基づいてIssue等を作成・登録するプロセスが手作業で行われており、非効率性やヒューマンエラーのリスクが課題となっています。

本ツールは、Markdown形式で記述された要件定義情報をAI（OpenAIまたはGemini）を用いて解析し、GitHub API（RESTおよびGraphQL）を介して必要なリソースを自動的に作成・設定することで、これらの課題解決を目指します。

### 1.2. 解決したい課題

- **非効率性:** 手作業によるGitHubリソースの作成・登録にかかる時間と工数の削減。
- **ヒューマンエラーのリスク:** Issue登録時の入力ミス、設定漏れ、担当者割り当てミスなどの削減。
- **標準化の欠如:** プロジェクトやIssue登録のフォーマット・粒度のばらつきを抑制し、管理を容易にする。
- **開発体験の低下:** 開発者が本来注力すべきタスクに集中できるよう、単純作業の繰り返しから解放する。

## 2. システム化の目的とゴール

### 2.1. システム化の目的

本システムの導入により、以下のビジネス目標達成を目指します。

- GitHubプロジェクトセットアップ（リポジトリ作成からIssue登録、関連付けまで）のリードタイムを大幅に短縮する。
- Issue登録に関する手作業起因のエラー発生率を削減する。
- 開発チーム内でのIssue管理プロセスの標準化を促進する。
- 開発者の満足度を向上させる。

### 2.2. 主要な成功基準

- 指定されたMarkdown形式のテキストファイルをインプットとし、CLI引数でリポジトリ名と（任意で）プロジェクト(v2)名が指定され、設定された生成AIによる解析を経て、GitHub上に **リポジトリ、ラベル、マイルストーン、およびIssue（タイトル、本文詳細、ラベル、マイルストーン、担当者を含む）** が自動で作成・設定（冪等性考慮）されること。さらに、指定された場合は作成されたIssueが **プロジェクト(v2)にアイテムとして追加** されること。
- ツールの操作が容易であり、開発者が日常的に利用できること (`Typer` を利用したCLI）。
- 処理結果（成功・失敗、スキップしたリソースの情報、エラー詳細含む）が明確にユーザーにフィードバックされること（`logging` および `CliReporter` を活用）。
- Dry Run モード (`--dry-run`) が提供され、実際の変更を行わずに実行結果をシミュレートできること。
- 実装された主要な機能コンポーネントに対してユニットテストが実装され、テストスイート全体が成功し、品質が担保されていること（目標カバレッジ 80%以上）。
- UI、UseCase、Domain、Infrastructure の各層が分離され、依存関係のルールが守られており、将来的な機能拡張や仕様変更に対応しやすい疎結合な設計（クリーンアーキテクチャ）であること。
- 設定によって**生成AIモデル（OpenAI, Gemini）を切り替え可能**であること。

## 3. スコープ定義

### 3.1. 対象範囲（In Scope）

- **入力:**
    - Markdown形式のテキストファイル（`--file` オプションでパス指定）。
    - CLI必須引数によるリポジトリ名 (`--repo`、形式: `owner/repo` または `repo`)。
    - CLI任意引数によるGitHub Project (V2) 名 (`--project`)。
    - CLI任意引数によるDry Runモード指定 (`--dry-run`)。
- **処理:**
    - **設定読み込み:** 環境変数または `.env` ファイルからGitHub PAT、AI APIキー、ログレベル、使用AIモデル等を `Pydantic-settings` を用いて安全に読み込み、検証する (`infrastructure/config.py`)。必須設定がない場合はエラー終了。
    - **ファイル読み込み:** 指定されたMarkdownファイルを読み込む (`infrastructure/file_reader.py`)。
    - **AI解析:** 設定された生成AI APIを用いてMarkdownテキストの内容を解析し、GitHubリソース情報（**Issueタイトル、本文詳細、ラベル、マイルストーン、担当者**）を抽出し、定義されたデータモデル (`domain/models.py`) に構造化する (`adapters/ai_parser.py`)。
    - **GitHub操作 (UseCase経由):**
        - `GitHubAppClient` (`githubkit` ベース) を利用してGitHub API (REST v3, GraphQL v4) と通信 (`adapters/github_client.py`)。
        - **リポジトリ作成/確認:** `CreateRepositoryUseCase` (`use_cases/create_repository.py`) が新規Privateリポジトリを作成（冪等）。オーナー名省略時は認証ユーザーを自動取得。
        - **ラベル作成/確認:** `CreateGitHubResourcesUseCase` が `GitHubAppClient.create_label` を呼び出し、AIが抽出したラベルが存在しなければ作成（冪等）。色は自動割り当て。エラー時も処理継続。
        - **マイルストーン作成/確認:** `CreateGitHubResourcesUseCase` が `GitHubAppClient.create_milestone` を呼び出し、AIが抽出したマイルストーン（複数ある場合は最初の1つ）が存在しなければ作成（冪等）。エラー時も処理継続。
        - **Issue作成/設定:** `CreateIssuesUseCase` (`use_cases/create_issues.py`) がAI解析結果に基づきIssueを作成。`GitHubAppClient.create_issue` を呼び出す際に、**タイトル、本文、抽出されたラベル、マイルストーンID（名前から解決）、担当者**を設定。同名Issueはスキップ。エラー時も処理継続（Issue単位）。成功時にIssueのURLとNode IDを取得。
        - **プロジェクト検索:** `--project` 指定時、`CreateGitHubResourcesUseCase` が `GitHubAppClient.find_project_v2_node_id` (GraphQL) を呼び出し、指定された名前のプロジェクト(v2)を検索。
        - **プロジェクトへのIssue追加:** プロジェクトが見つかり、Issueが作成された場合、`CreateGitHubResourcesUseCase` が `GitHubAppClient.add_item_to_project_v2` (GraphQL) を呼び出し、作成されたIssueをプロジェクトにアイテムとして追加。エラー時も処理継続（アイテム単位）。
    - **ワークフロー制御:** `CreateGitHubResourcesUseCase` (`use_cases/create_github_resources.py`) が上記ステップ（リポジトリ->ラベル->マイルストーン->プロジェクト検索->Issue作成->プロジェクト追加）をオーケストレーションする。致命的エラー発生時は処理を中断し例外を送出。
- **出力:**
    - 標準出力/標準エラー出力: 処理の進行状況、最終結果サマリー、エラーメッセージ (`logging` を利用)。
    - 結果表示: `CliReporter` (`adapters/cli_reporter.py`) がUseCaseの結果オブジェクト (`CreateGitHubResourcesResult`) を整形してログに出力。
- **実行形態:** コマンドラインインターフェース (CLI) アプリケーション (`Typer` を利用、`main.py` がエントリーポイント)。
- **開発言語:** Python (3.10 以上、テスト環境 3.13.3)。
- **認証:** GitHub Personal Access Token (PAT)、生成AI APIキー。

### 3.2. 対象範囲外（Out of Scope）

- WebアプリケーションとしてのUI開発。
- 入力テキストファイルの作成支援。
- Markdown以外の入力フォーマットサポート。
- AIによる担当者の**推測**機能。
- GitHub以外のプラットフォーム対応。
- 複雑なエラーリカバリ処理。
- GUIインストーラー。
- 生成AIのFine-tuning。
- Issue間の親子関係や依存関係の自動設定。
- Pull Request の自動作成。
- GitHub Projects (V2) の新規作成。
- リポジトリのコラボレーター設定、Issue/PRテンプレート適用、ブランチ保護ルール設定。
- Markdownファイル全体で共通のラベル・マイルストーンを定義・利用する機能。
- 複数のマイルストーン名をファイル内で定義し、個別に処理する機能。
- ラベル作成時の色・説明の指定機能。
- プロジェクトへのアイテム追加時にステータス等のフィールドを設定する機能。

## 4. 主要なステークホルダーと役割

- **開発者:** 主要ユーザー。セットアップ作業の効率化。
- **プロジェクトマネージャー (PM):** プロジェクト管理の効率化・標準化。入力テキストの記述スタイル策定に関与。

## 5. ユースケース定義

### 5.1. UC-001: テキストファイルからGitHubリソースを自動登録する

- **アクター:** 開発者、プロジェクトマネージャー
- **事前条件:** Docker実行環境、有効なPAT/APIキー設定済み（環境変数or `.env`）、入力Markdownファイル存在、CLI引数（`--file`, `--repo`）指定、PATに必要な権限（repo, project）があること。
- **事後条件:** Markdown内容に基づき、指定されたGitHubリソース（リポジトリ、ラベル、マイルストーン、Issue）が作成/設定（重複スキップ含む）される。`--project` が指定され、プロジェクトが存在すれば、作成されたIssueがプロジェクトにアイテムとして追加される。処理結果（成功・失敗・スキップ情報、エラー詳細）がユーザーに表示される。
- **基本フロー (概要):**
    1. `main.py`: CLI引数解析、設定読み込み。
    2. `main.py`: ファイル読み込み (`read_markdown_file`)。
    3. `main.py`: AI解析 (`AIParser.parse`) -> `ParsedRequirementData` 取得。
    4. `main.py`: 依存関係（`GitHubAppClient`, UseCases）を準備し、`CreateGitHubResourcesUseCase` をインスタンス化。
    5. `main.py`: `CreateGitHubResourcesUseCase.execute(parsed_data, repo_name_input, project_name, dry_run)` を呼び出す。
    6. `CreateGitHubResourcesUseCase`: リポジトリ名解析 (`_get_owner_repo`)。
    7. `CreateGitHubResourcesUseCase`: Dry Run モードでなければ以下を実行。
    8. `CreateGitHubResourcesUseCase`: `CreateRepositoryUseCase.execute` でリポジトリ作成/確認。
    9. `CreateGitHubResourcesUseCase`: `ParsedRequirementData` からラベル名を収集し、`GitHubAppClient.create_label` で作成/確認（エラー記録）。
    10. `CreateGitHubResourcesUseCase`: `ParsedRequirementData` からマイルストーン名を収集し、`GitHubAppClient.create_milestone` で作成/確認（エラー記録）。
    11. `CreateGitHubResourcesUseCase`: `project_name` があれば `GitHubAppClient.find_project_v2_node_id` で検索（エラー記録）。
    12. `CreateGitHubResourcesUseCase`: `CreateIssuesUseCase.execute` でIssue作成（エラー記録）。
    13. `CreateGitHubResourcesUseCase`: プロジェクトIDとIssue Node IDがあれば `GitHubAppClient.add_item_to_project_v2` でアイテム追加（エラー記録）。
    14. `CreateGitHubResourcesUseCase`: `CreateGitHubResourcesResult` を構築して返却。
    15. `main.py`: 受け取った結果を `CliReporter.display_create_github_resources_result` で表示。
- **代替フロー（例外フロー）:**
    - 各ステップで致命的エラーが発生した場合、UseCaseは例外を送出し、`main.py` が捕捉してエラー情報を表示し、非ゼロコードで終了する。
    - ラベル、マイルストーン、Issue作成、プロジェクト連携の各ステップでのエラーは、UseCase内で捕捉・記録され、可能な限り処理は続行される。最終結果にエラー情報が含まれる。

## 6. ドメインモデル

- **データモデル (Pydantic):**
    - `IssueData`: title, description, tasks (list), relational_definition (list[str]), relational_issues (list[str]), acceptance (list[str]), labels (list[str]|None), milestone (str|None), assignees (list[str]|None)。
    - `ParsedRequirementData`: `issues: list[IssueData]`。
    - `CreateIssuesResult`: created_issue_details (list[tuple[str, str]]), skipped_issue_titles (list[str]), failed_issue_titles (list[str]), errors (list[str])。
    - `CreateGitHubResourcesResult`: repository_url (str|None), project_node_id (str|None), project_name (str|None), created_labels (list[str]), failed_labels (list[tuple[str,str]]), milestone_name (str|None), milestone_id (int|None), milestone_creation_error (str|None), issue_result (CreateIssuesResult|None), project_items_added_count (int), project_items_failed (list[tuple[str,str]]), fatal_error (str|None)。
- **ドメイン例外 (Exceptions):**
    - `GitHubClientError` (基底)
    - `GitHubAuthenticationError`
    - `GitHubRateLimitError`
    - `GitHubResourceNotFoundError`
    - `GitHubValidationError`
    - `AiParserError`

## 7. 機能要件 (一覧 - 実装済み)

- **FR-001:** Markdownファイル読み込み
- **FR-002:** AIによる情報抽出 (Title, Body, Labels, Milestone, Assignees)
- **FR-003:** GitHubリポジトリ作成/確認 (Private, Auto-init, Idempotent, Owner Infer)
- **FR-004:** GitHub Issue作成 (Title, Body, Labels, Milestone Name, Assignees, Idempotent Title Check)
- **FR-005:** GitHub ラベル作成/確認 (Idempotent)
- **FR-006:** GitHub マイルストーン作成/確認 (Idempotent, First-only)
- **FR-007:** GitHub Issueへの担当者割り当て (Issue作成時)
- **FR-008:** GitHub Project (V2) へのアイテム追加 (Optional, Find by Name, Add by ID)
- **FR-009:** Dry Run モード

## 8. 非機能要件 (一覧 - 実装済み/考慮済み)

- **NFR-Err-01:** 詳細なエラーハンドリング（カスタム例外）
- **NFR-Err-02:** 部分的エラー発生時の処理継続
- **NFR-Log-01:** Python標準 `logging` 使用
- **NFR-Log-02:** ログレベル設定可能 (`LOG_LEVEL`)
- **NFR-Log-03:** 整形された結果レポート出力 (`CliReporter`)
- **NFR-Cfg-01:** `.env`/環境変数による設定 (`pydantic-settings`)
- **NFR-Cfg-02:** 必須設定（PAT, APIキー, AIモデル）の検証
- **NFR-Lib-01:** 主要外部ライブラリ利用 (`typer`, `pydantic`, `githubkit`, `openai`, `google-genai`, `dotenv`)
- **NFR-Sec-01:** 機密情報管理 (`SecretStr`, `.gitignore`)
- **NFR-Arch-01:** クリーンアーキテクチャ（層分離）
- **NFR-Test-01:** ユニットテスト実装 (`pytest`, `unittest.mock`)
- **NFR-Test-02:** コードカバレッジ計測 (`pytest-cov`、目標80%達成)
- **NFR-Lang-01:** Python 3.10+
- **NFR-AI-01:** AIモデル切り替え可能 (`AI_MODEL`)
- **NFR-AI-02:** AI解析結果の手動確認・修正が必要になる可能性

## 9. 受け入れ基準 (Acceptance Criteria)

- **AC-Core-Flow:** CLI実行（必須引数指定）により、Markdown内容に基づいてリポジトリ、ラベル、マイルストーン、Issue（関連情報含む）がGitHub上に冪等性を保ちつつ作成される。
- **AC-Project-Link:** `--project` 指定時に、存在するプロジェクトが正しく検索され、作成されたIssueがアイテムとして追加される。プロジェクトが存在しない場合は警告が表示され、アイテム追加はスキップされる。
- **AC-Dry-Run:** `--dry-run` 指定時に、GitHubへの書き込み操作が行われず、実行されるであろう操作のログが出力される。
- **AC-Owner-Infer:** `--repo` に `repo-name` のみ指定した場合、認証ユーザー名がオーナーとして使用される。
- **AC-Error-Handling:** 想定されるエラー（設定不備、ファイルエラー、APIエラー、AIエラー）発生時に、適切なメッセージが表示され、非ゼロコードで終了する。部分的なエラー（ラベル作成失敗など）では処理が継続し、最終結果に記録される。
- **AC-Tests-Pass:** `pytest` 実行時にすべてのテスト（118件）が成功する。

## 10. 用語集

- **要件定義ファイル (Requirement File):** 本ツールが入力として受け取る、GitHubリソース情報をMarkdown形式で記述したテキストファイル。
- **生成AI (Generative AI):** テキスト解析に利用するAI（OpenAI GPTモデル, Google Geminiモデル）。
- **解析 (Parse):** 生成AIがMarkdownテキストの内容を解釈し、GitHubリソース情報を含む構造化データ (`ParsedRequirementData`) を出力するプロセス。
- **登録 (Register / Create / Apply):** 解析結果やCLI引数を元に、GitHub APIを通じて実際にGitHub上にリソースを作成・設定するプロセス。
- **冪等性 (Idempotency):** ある操作を1回行っても複数回行っても結果が同じであるという性質。
- **スキップ (Skip):** 重複するリソース（リポジトリ、Issueタイトル）の作成を回避すること。
- **PAT (Personal Access Token):** GitHub APIを利用するための認証トークン。
- **APIキー (API Key):** 生成AI APIを利用するための認証キー。
- **CLI (Command Line Interface):** 本ツールが提供するユーザーインターフェース (`Typer`)。
- **プロジェクトV2 (Project V2):** GitHubの新しいバージョンのプロジェクト機能。
- **Node ID:** GraphQL APIでリソースを一意に識別するためのID。
- **UseCase (Interactor):** アプリケーション固有のビジネスロジックや処理フローを実行するコンポーネント。
- **Adapter:** UseCase層と外部要素（UI, DB, 外部API）を繋ぐコンポーネント。
- **Dry Run:** 実際には変更を加えず、実行されるであろう操作をシミュレートするモード。

## 11. 制約条件・前提条件

- **開発言語:** Python 3.10 以上 (テスト環境 3.13.3)。
- **実行環境:** Docker上のLinux環境推奨。インターネット接続が必要。
- **外部依存:**
    - GitHub API (REST v3, GraphQL v4)
    - OpenAI API または Google Generative AI API
    - 主要ライブラリ: `typer`, `pydantic`, `pydantic-settings`, `githubkit`, `openai`, `google-generativeai`, `python-dotenv`, `pytest`, `pytest-cov`, `unittest.mock`.
- **認証:** 有効なGitHub PAT (スコープ: `repo`, `project`) と、選択されたAIモデルに対応する有効なAPIキーが、環境変数または `.env` ファイル経由で提供されること。
- **入力フォーマット:** UTF-8 Markdownファイル。AIが解釈しやすい構造推奨。
- **AIの前提:** AIの解析結果は完全ではなく、**手動確認・修正が必要になる可能性がある**ことを前提とする。
