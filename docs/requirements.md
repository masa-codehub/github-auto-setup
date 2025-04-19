# 要件定義書: GitHubリソース自動登録ツール

## 1. 概要と背景

### 1.1. プロジェクトの目的と背景

本プロジェクトは、ソフトウェア開発プロセスにおけるGitHub上のセットアップ作業（プロジェクト作成、リポジトリ作成、Issue登録など）の効率化を目的とします。現状、これらの作業、特に要件定義書に基づいてIssue、マイルストーン、ラベル等を作成・登録するプロセスが手作業で行われており、非効率性やヒューマンエラーのリスクが課題となっています。

提供された「要件定義書からのGitHubプロジェクト・リポジトリ・Issue自動作成に関する調査報告書」に基づき、これらの課題を解決するための自動化ツールを開発します。

### 1.2. 解決したい課題

- **非効率性:** 手作業によるGitHubリソースの作成・登録にかかる時間と工数の削減。
- **ヒューマンエラーのリスク:** Issue登録時の入力ミス、設定漏れ、担当者割り当てミスなどの削減。
- **標準化の欠如:** プロジェクトやIssue登録のフォーマット・粒度のばらつきを抑制し、管理を容易にする。
- **開発体験の低下:** 開発者が本来注力すべきタスクに集中できるよう、単純作業の繰り返しから解放する。

## 2. システム化の目的とゴール

### 2.1. システム化の目的

本システムの導入により、以下のビジネス目標達成を目指します。

- GitHubプロジェクトセットアップのリードタイムを **[具体的な目標値]%短縮** する。
- Issue登録に関する手作業起因のエラー発生率を **[具体的な目標値]%削減** する。
- 開発チーム内でのIssue管理プロセスの標準化を促進する。
- 開発者の満足度を向上させる。

### 2.2. 主要な成功基準

- 指定されたMarkdown形式のテキストファイルをインプットとし、**CLI引数でリポジトリ名・プロジェクト名が指定**され、**生成AI (LangChain経由)** による解析を経て、GitHub上に**リポジトリ、ラベル、マイルストーン、プロジェクト(v2)、およびIssue（タイトル、本文詳細、ラベル、マイルストーン、担当者を含む）**が自動で作成・設定（冪等性考慮）されること。
- ツールの操作が容易であり、開発者が日常的に利用できること (`Typer` を利用したCLI）。
- 処理結果（成功・失敗、スキップしたIssueの情報、エラー詳細含む）が明確にユーザーにフィードバックされること（`logging` および `CliReporter` を活用）。
- （TDD観点）実装された主要な機能コンポーネント（CLI, FileReader, Config, AIParser, GitHubClient, 各UseCases, Reporter）に対してユニットテストが実装され、品質が担保されていること (`pytest`, `unittest.mock`, `pytest-cov` を利用）。
- （Clean Architecture観点）UI、UseCase、Domain、Infrastructure の各層が分離され、依存関係のルールが守られており、将来的な機能拡張（例: Web UI化、Django連携）や仕様変更に対応しやすい疎結合な設計であること。
- LangChainを利用し、設定によって**生成AIモデル（OpenAI, Gemini等）を切り替え可能**であること。

## 3. スコープ定義

### 3.1. 対象範囲（In Scope）

- **入力:**
    - Markdown形式のテキストファイル（`--file` オプションでパス指定）。
    - CLI必須引数によるリポジトリ名 (`--repo`、形式: `owner/repo` または `repo`)、プロジェクト名 (`--project`) の指定。
    - (オプション) 設定ファイルパス (`--config`、現時点では未使用)、ドライラン実行 (`--dry-run`) の指定。
- **処理:**
    - **設定読み込み:** 環境変数または `.env` ファイルからGitHub PAT、AI APIキー、ログレベル、使用AIモデル等を `Pydantic-settings` を用いて安全に読み込み、検証する (`infrastructure/config.py`)。必須設定がない場合はエラー終了。
    - **ファイル読み込み:** 指定されたMarkdownファイルを読み込む (`infrastructure/file_reader.py`)。
    - **AI解析:** `LangChain` フレームワークを利用し、設定された生成AI APIを用いてMarkdownテキストの内容を解析し、GitHubリソース情報（**Issueタイトル、本文詳細、ラベル、マイルストーン、担当者**）を抽出し、定義されたデータモデル (`domain/models.py`) に構造化する (`adapters/ai_parser.py`)。
    - **GitHub操作 (UseCase経由):**
        - `GitHubAppClient` (`githubkit` ベース) を利用してGitHub APIと通信 (`adapters/github_client.py`)。
        - **リポジトリ作成:** `CreateRepositoryUseCase` (`use_cases/create_repository.py`) が新規Privateリポジトリを作成（冪等）。
        - **ラベル作成/確認:** `CreateGitHubResourcesUseCase` が `GitHubAppClient.create_label` を呼び出し、AIが抽出したラベルが存在しなければ作成（冪等）。色は自動割り当て。
        - **マイルストーン作成/確認:** (将来実装) UseCaseが `GitHubAppClient.create_milestone` を呼び出し、AIが抽出したマイルストーンが存在しなければ作成（冪等）。
        - **プロジェクト作成/確認:** (将来実装) UseCaseが `GitHubAppClient` を呼び出し、指定された名前のプロジェクト(v2)が存在しなければ作成（冪等）。
        - **Issue作成/設定:** `CreateIssuesUseCase` (`use_cases/create_issues.py`) がAI解析結果に基づきIssueを作成。`GitHubAppClient.create_issue` を呼び出す際に、**タイトル、本文、抽出されたラベル、マイルストーンID、担当者**を設定。同名Issueはスキップ。エラー時も処理継続（Issue単位）。
        - **プロジェクトへのIssue追加:** (将来実装) UseCaseが `GitHubAppClient` を呼び出し、作成されたIssueを指定されたプロジェクトに追加。
    - **ワークフロー制御:** `CreateGitHubResourcesUseCase` (`use_cases/create_github_resources.py`) が上記ステップをオーケストレーションする。エラー発生時は処理を中断し例外を送出。
- **出力:**
    - 標準出力/標準エラー出力: 処理の進行状況、最終結果サマリー、エラーメッセージ (`logging` を利用)。
    - 結果表示: `CliReporter` (`adapters/cli_reporter.py`) がUseCaseの結果オブジェクト (`CreateIssuesResult` 等) やエラー情報を整形してログに出力。
- **実行形態:** コマンドラインインターフェース (CLI) アプリケーション (`Typer` を利用、`main.py` がエントリーポイント)。
- **開発言語:** Python (3.13.3)。
- **依存関係管理:** `pip-tools` を使用 (`requirements.in`, `requirements.txt`)。
- **認証:** GitHub Personal Access Token (PAT)、生成AI APIキー。

### 3.2. 対象範囲外（Out of Scope）

- WebアプリケーションとしてのUI開発（将来的な考慮はする）。
- 入力テキストファイルの作成支援。
- 規約ベースのパーサー実装。
- AIによる担当者の**推測**機能（特定記法の解析は対象内）。
- GitHub以外のプラットフォーム対応。
- 複雑なエラーリカバリ処理: エラー発生時はログ/メッセージ表示の上で基本的に処理中断。Issue作成時のエラーは該当Issueをスキップし処理継続。
- GUIインストーラー。
- 生成AIのFine-tuning。
- **Issue間の親子関係や依存関係の自動設定。**
- **Pull Request の自動作成。**

## 4. 主要なステークホルダーと役割

- **開発者:** 主要ユーザー。セットアップ作業の効率化。
- **プロジェクトマネージャー (PM):** プロジェクト管理の効率化・標準化。入力テキストの記述スタイル策定に関与。
- **システム管理者/運用担当:** (Webアプリ化した場合) デプロイ・運用。
- **(DDD観点)**: 開発者・PMのドメイン知識を基に**ユビキタス言語**（後述）を定義・共有。

## 5. ユースケース定義

### 5.1. UC-001: テキストファイルからGitHubリソースを自動登録する

- **アクター:** 開発者、プロジェクトマネージャー
- **事前条件:** Docker実行環境、有効なPAT/APIキー設定済み、入力Markdownファイル存在、CLI引数（`--file`, `--repo`, `--project`）指定、PATに必要な権限があること。
- **事後条件:** Markdown内容に基づき、指定されたGitHubリソース（リポジトリ、ラベル、マイルストーン、プロジェクト、Issue）が作成/設定（重複スキップ含む）される。処理結果がユーザーに表示される。
- **基本フロー (by `CreateGitHubResourcesUseCase`):**
    1. CLI (`main.py`) が引数を解析し、依存関係を準備して `CreateGitHubResourcesUseCase` をインスタンス化し、`execute` を呼び出す。
    2. UseCase: リポジトリ名を解析し、ownerとrepo名を取得。
    3. UseCase: `FileReader` でファイル内容を取得。
    4. UseCase: `AIParser` でファイル内容を解析し、`ParsedRequirementData` (Issueリスト、ラベル、マイルストーン、担当者情報を含む) を取得。
    5. UseCase: `dry_run` が False なら続行。
    6. UseCase: `CreateRepositoryUseCase` を呼び出しリポジトリを作成。結果を `Reporter` で表示。
    7. UseCase: **`GitHubAppClient.create_label` を呼び出し、解析結果のラベルを作成（冪等）。結果をログ記録。**
    8. UseCase: **(将来) `GitHubAppClient.create_milestone` を呼び出し、解析結果のマイルストーンを作成（冪等）。結果をログ記録。**
    9. UseCase: **(将来) `GitHubAppClient.create_project` (仮) を呼び出し、プロジェクトを作成（冪等）。結果をログ記録。**
    10. UseCase: `CreateIssuesUseCase` を呼び出し、Issueを作成（ラベル、マイルストーン、担当者設定含む、重複スキップ）。結果 (`CreateIssuesResult`) を `Reporter` で表示。
    11. UseCase: **(将来) `GitHubAppClient.add_item_to_project` (仮) を呼び出し、作成したIssueをプロジェクトに追加。結果をログ記録。**
    12. UseCase: 正常完了ログを出力。
- **代替フロー（例外フロー）:**
    - いずれかのステップでエラーが発生した場合、UseCaseは例外を送出し、`main.py` が捕捉してエラー情報を表示し、非ゼロコードで終了する。Issue作成中のエラーは `CreateIssuesUseCase` が内部でハンドリングし、結果オブジェクトに含める。
- **(Clean Architecture観点)**: `main.py` (UI) -> `CreateGitHubResourcesUseCase` (UseCase) -> 各種コンポーネント (Adapters, Domain Models) の依存関係フロー。

## 6. ドメインモデル

- **エンティティ (Entity):** `Repository`, `Issue`, `Label`, `Milestone`, `Project`
- **値オブジェクト (Value Object):** `FilePath`, `GitHubCredentials`, `AiApiCredentials`, `RepositoryName`, `ProjectName`, `LabelName`, `LabelColor`, `MilestoneTitle`, `Assignee`
- **データ転送オブジェクト (DTO - Pydantic Models):**
    - `IssueData`: title, description, tasks (list[str]), relational_definition (list[str]), relational_issues (list[str]), acceptance (list[str]), labels (list[str]|None), milestone (str|None), assignees (list[str]|None)。
    - `ParsedRequirementData`: `issues: list[IssueData]`。将来的には共通ラベル等も。
    - `CreateIssuesResult`: created_issue_urls, skipped_issue_titles, failed_issue_titles, errors。
- **集約 (Aggregate):** `Repository` (Issues, Labels, Milestones を含む), `Project` (Items を含む)
- **ドメインサービス:** 明示的なものは定義せず、UseCase層またはAdapter層が責務を持つ。
- **(DDD観点)**: ユビキタス言語を定義・活用し、ドメイン境界を意識する。

## 7. 機能要件

_(主要なものを抜粋・更新)_

- **FR-Core-001:** CLI引数で指定されたMarkdownファイルを読み込む。(`read_markdown_file`)
- **FR-Core-002:** 環境変数/`.env`から設定値（PAT, APIキー等）を安全に読み込む。(`load_settings`, `Settings`)
- **FR-Core-003:** LangChain+AIを使用し、MarkdownからIssue情報（**Title, Body詳細, Labels, Milestone, Assignees**）を抽出し構造化する。(`AIParser.parse`)
- **FR-Core-004:** CLI引数で指定された名前で新規Privateリポジトリを作成（冪等）。(`CreateRepositoryUseCase`)
- **FR-Core-005:** AI解析結果に基づき、リポジトリに必要なラベルを作成（冪等、色は自動）。(`GitHubAppClient.create_label` を UseCase から呼び出し)
- **FR-Core-006:** (将来) AI解析結果に基づき、リポジトリに必要なマイルストーンを作成（冪等）。
- **FR-Core-007:** AI解析結果に基づき、リポジトリにIssueを作成。**タイトル、本文、ラベル、マイルストーンID、担当者**を設定。同名Issueはスキップ。エラー時継続。(`CreateIssuesUseCase`, `GitHubAppClient.create_issue`)
- **FR-Core-008:** (将来) CLI引数で指定された名前でプロジェクト(v2)を作成（冪等）。
- **FR-Core-009:** (将来) 作成されたIssueを、CLI引数で指定されたプロジェクトに追加。
- **FR-Infra-001:** GitHub APIクライアント (`GitHubAppClient`) 実装。
    - **実装済:** Repo作成, Issue検索, Issue作成(Labels, MilestoneID, Assignees 設定可), Label作成/取得, Milestone検索/作成。
    - **未実装:** プロジェクト作成/検索, Issueのプロジェクト追加。
- **FR-Infra-002:** 処理結果を整形してログ/標準出力に表示。(`CliReporter`)
- **FR-Infra-003:** LangChainによるAIモデル切替機能。(`AIParser._initialize_llm`)
- **FR-UI-001:** CLIインターフェース (`Typer`) 実装。必須・オプション引数定義。 (`main.py`)
- **FR-Flow-001:** `main.py` から `CreateGitHubResourcesUseCase` を呼び出し、**リポジトリ作成->ラベル作成->Issue作成** のコアフローを実行。適切なエラーハンドリング。

## 8. 非機能要件

- **性能:**
    - NFR-Perf-01: GitHub/AI APIレート制限、レスポンスタイム、コスト考慮。目標: **[TBD]**。
    - NFR-Perf-02: 妥当なメモリ使用量。
- **可用性:**
    - NFR-Avail-01: Docker環境、ネットワーク接続、外部API稼働に依存。
- **セキュリティ:**
    - NFR-Sec-01: PAT/APIキーは `.env`/環境変数から`Pydantic-settings` (`SecretStr`) で読み込み。コード埋め込み禁止。`.env` は `.gitignore`。
    - NFR-Sec-02: `pip-tools` で依存関係固定。脆弱性チェック検討。
- **保守性/拡張性:**
    - NFR-Maint-01: クリーンアーキテクチャ (UI, UseCase, Domain, Infrastructure)。
    - NFR-Maint-02: 設定値 (プロンプト, AIモデル等) は `Pydantic-settings` で外部設定可能に。
    - NFR-Maint-03: Python 3.13.3。型ヒント (`list[str]`, `| None` スタイル), 静的解析 (Ruff, mypy)。
    - NFR-Maint-04: 可読性, モジュール分割, テストによるドキュメント。
    - NFR-Maint-05: Django連携考慮 (UseCase層のAPI化)。
    - NFR-Maint-06改: LangChainによるモデル切り替え容易性。
- **テスト容易性:**
    - NFR-Test-01: UseCase/Domain層のユニットテスト容易性。
    - NFR-Test-02: Infrastructure層のモック容易性 (`unittest.mock`)。
    - NFR-Test-03: CLIのE2Eに近いテスト (`CliRunner`)。目標カバレッジ **[目標値: 80%以上]**。
- **UI/UX (CLI):**
    - NFR-UIUX-01: 引数・オプションは直感的。
    - NFR-UIUX-02: `--help` は十分な情報を提供（段階的改善）。
    - NFR-UIUX-03: 進行状況、結果、エラー、スキップ情報は `logging` で具体的に表示。
- **AI利用に関する考慮事項:**
    - NFR-AI-01: **手動での確認・修正前提**。
    - NFR-AI-02: API利用**コスト**意識。
    - NFR-AI-03: 再現性は必須ではないが `temperature=0` 等で抑制。

## 9. 受け入れ基準 (Acceptance Criteria)

_(主要なものを抜粋・更新)_

- **AC-Core-Flow-With-Labels:**
    - **Given** 必須環境変数設定済み、Issue Title/Body詳細/Labels/Milestone(Title)/Assignee(記法) を含む `test.md` が存在。
    - **When** `gh-auto-tool run --file test.md --repo owner/new-repo --project "New Project"` を実行。
    - **Then** GitHub上に `owner/new-repo` (Private) が作成され、`test.md` 内のラベルが存在しなければ作成され、マイルストーンが存在しなければ作成され (ID取得)、Issueがタイトル・本文・**ラベル**・**マイルストーン**・**担当者**付きで作成される。プロジェクトは(現時点では)作成されない。ログ/標準出力に成功/スキップ/失敗情報とURLが表示される。終了コードは0。
- **AC-Issue-Skip:** (変更なし)
- **AC-Config-Error:** (変更なし)
- **AC-AI-Error:** (変更なし)
- **AC-File-Not-Found:** (変更なし)
- **AC-Args-Missing:** (変更なし)
- **AC-All-Tests-Pass:** プロジェクト内の全ユニットテストが成功する。

## 10. 用語集

- **要件定義ファイル (Requirement File):** 本ツールが入力として受け取る、GitHubリソース情報をMarkdown形式で記述したテキストファイル。
- **生成AI (Generative AI):** テキスト解析に利用するAI（ChatGPT API, Gemini API等）。
- **LangChain:** 生成AIアプリケーション開発フレームワーク。
- **解析 (Parse / Interpretation):** 生成AIがMarkdownテキストの内容を解釈し、GitHubリソース情報を含む構造化データを出力するプロセス。
- **プロンプト (Prompt):** 生成AIに解析を依頼する際の指示文。
- **登録 (Register / Create / Apply):** 解析結果を元に、GitHub API/CLIを通じて実際にGitHub上にリソースを作成・設定するプロセス。
- **冪等性 (Idempotency):** ある操作を1回行っても複数回行っても結果が同じであるという性質。
- **スキップ (Skip):** 重複するIssueの作成を回避すること。その事実は記録・表示される。
- **PAT (Personal Access Token):** GitHub APIを利用するための認証トークン。
- **APIキー (API Key):** 生成AI APIを利用するための認証キー。
- **CLI (Command Line Interface):** 本ツールが提供するユーザーインターフェース形式 (`Typer` を使用)。
- **プロジェクトV2 (Project V2):** GitHubの新しいバージョンのプロジェクト機能。
- **pip-tools:** Pythonの依存関係を `requirements.in` から `requirements.txt` にコンパイル・管理するツール。
- **Pydantic-settings:** Pydanticモデルを用いて環境変数や `.env` ファイルから設定値を読み込み、型検証を行うライブラリ。
- **依存性注入 (DI):** クラスが必要とする他のオブジェクト（依存関係）を、外部から（主にコンストラクタ経由で）与える設計パターン。
- **UseCase (Interactor):** アプリケーション固有のビジネスロジックや処理フローを実行するコンポーネント。
- **Adapter:** UseCase層と外部要素（UI, DB, 外部API）を繋ぐコンポーネント。
- **ユビキタス言語:** プロジェクト関係者（開発者、PMなど）が共通認識を持つための用語体系。上記太字などが候補。

## 11. 制約条件・前提条件

- **開発言語:** Python 3.13.3 (Dockerイメージに基づく)。
- **実行環境:** Docker上のLinux環境。インターネット接続が必要。
- **外部依存:**
    - **GitHub API:** `githubkit` ライブラリ経由でアクセス。
    - **生成AI API:** OpenAI API または Google Generative AI API (設定で切替)。
    - **主要ライブラリ:** `langchain`, `langchain-openai`, `langchain-google-genai`, `typer`, `pydantic-settings`, `python-dotenv`, `githubkit`。
    - **開発・テストツール:** `pip-tools`, `pytest`, `pytest-cov`, `unittest.mock`, `ruff`, `mypy`。
- **認証:** 有効なGitHub PAT (repo, projectスコープ等が必要) と、選択されたAIモデルに対応する有効なAPIキーが、環境変数または `.env` ファイル経由で提供されること。
- **入力フォーマット:** 要件定義ファイルはMarkdown形式。AIが解釈しやすい構造推奨。担当者情報は特定記法（例: `Assignee: @user`)がある場合のみ対象。
- **リポジトリ・プロジェクト名:** CLI引数 (`--repo`, `--project`) で指定必須。
- **機能実装スコープ(v1.0目標):** CLI提供。AIによるIssue(Title, Body詳細, Labels, Milestone Title, Assignees記法)抽出。GitHubリポジトリ新規作成。ラベル・マイルストーン作成(冪等)。Issue作成(Title, Body, Labels, Milestone ID, Assignees設定、重複スキップ)。プロジェクト作成(冪等)。Issueのプロジェクトへの追加。
- **AIの前提:** AIの解析結果は完全ではなく、**手動確認・修正が必要になる可能性がある**ことを前提とする。