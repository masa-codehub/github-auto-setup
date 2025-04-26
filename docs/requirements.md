# 要件定義書: GitHub Automation Tool

**バージョン:** 1.6
**最終更新日:** 2025-04-26 (JST)
**ステータス:** 仕様確定

## 1. 概要と背景

* **プロジェクトの目的、開発に至った背景:**
    ソフトウェア開発プロジェクトにおける GitHub セットアップ作業（リポジトリ作成、Markdown 要件定義からの Issue 一括登録、ラベル・マイルストーン設定、プロジェクト連携）の自動化と効率化を目指します。手作業による時間的コスト、ヒューマンエラー、標準化の欠如といった課題を解決することを目的とします。
    * **クリーンアーキテクチャ観点:** 外部システム（AI、GitHub API）への依存を Adapters 層に閉じ込め、ドメインロジックやユースケースの変更容易性を確保します。
* **解決したい課題:**
    * 手作業による GitHub リソース作成・登録時間の削減。
    * Issue 登録時の入力ミス、設定漏れ、無効な担当者指定による作成失敗などのエラー削減。
    * プロジェクト横断での Issue 登録フォーマット・粒度の標準化促進。
    * 開発者が価値の高いタスクに集中できる環境の提供。

## 2. システム化の目的とゴール

* **このシステムを導入することで達成したい具体的なビジネス目標:**
    * GitHub プロジェクト初期セットアップ（リポジトリ作成〜Issue 登録・連携）のリードタイムを 50% 以上短縮する（目標値）。
    * Issue 登録に関する手作業起因のエラー発生率を現状の 10% 以下に削減する（目標値）。
    * 開発チーム内での Issue 管理プロセス標準化を推進し、プロジェクト管理コストを削減する。
    * 開発者の定型作業負荷を軽減し、満足度を向上させる。
* **システムが満たすべき主要な成功基準:**
    * **機能:** 指定された Markdown ファイルと CLI 引数を基に、設定された生成 AI (OpenAI/Gemini) が情報を解析し、GitHub 上にリポジトリ、ラベル、ファイル内で言及された全てのマイルストーン、Issue (タイトル、本文、ラベル、Issueごとに指定されたマイルストーン、検証済みの担当者) を冪等性を保ちつつ自動作成・設定できること。AI が抽出した担当者は、Issue 作成前に GitHub API で有効性を検証し、無効な担当者は除外すること。 指定された場合は GitHub Projects (V2) に作成した Issue をアイテムとして追加できること。
    * **操作性:** 開発者が容易に利用できる CLI (`Typer`) を提供すること。
    * **フィードバック:** 処理結果 (成功、失敗、スキップ、検証に失敗した担当者、エラー詳細) をログ (`logging`) および整形されたレポート (`CliReporter`) で明確にユーザーに提示すること。
    * **安全性:** Dry Run モード (`--dry-run`) で実際の変更前に実行結果をシミュレーションできること。
    * **品質 (TDD観点):** 主要な機能コンポーネント (UseCase, Adapters, Domain Models) に対するユニットテストが実装され、テストスイートが常に成功し、コードカバレッジ 80% 以上を維持すること。
    * **保守性/拡張性 (Clean Architecture観点):** UI (CLI)-UseCase-Domain-Infrastructure の各層が明確に分離され、依存関係のルール (内側への依存のみ許可) が遵守されていること。
    * **柔軟性:** 設定ファイルまたは環境変数により、使用する生成 AI モデル (OpenAI/Gemini) を切り替え可能であること。

## 3. スコープ定義

* **対象範囲（In Scope）:**
    * **入力:**
        * UTF-8 エンコードされた Markdown テキストファイル (`--file`)。AI が解析しやすい推奨フォーマットのテンプレートを提供する予定です **(具体的なルール定義は TBD)**。
        * CLI 引数: リポジトリ名 (`--repo`、`owner/repo` または `repo` 形式)、GitHub Project (V2) 名 (`--project`、任意)、Dry Run フラグ (`--dry-run`、任意)。
    * **処理:**
        * **設定読み込み (`infrastructure/config.py`):** `.env` または環境変数から GitHub PAT, AI API キー (OpenAI/Gemini), AI モデル名, ログレベル を `Pydantic-settings` で読み込み、検証します。必須項目欠落時はエラー終了します。
        * **ファイル読み込み (`infrastructure/file_reader.py`):** 指定された Markdown ファイルの内容を読み込みます。
        * **AI 解析 (`adapters/ai_parser.py`):** 設定された AI モデル (LangChain 経由) を使用し、Markdown テキストから Issue 情報 (タイトル, 説明, タスクリスト, 関連要件リスト, 関連 Issue リスト, 受け入れ基準リスト, ラベルリスト, Issueごとのマイルストーン名, 担当者リスト) を抽出し、`ParsedRequirementData` ドメインモデル (`domain/models.py`) にマッピングします。**AI の解析結果が Pydantic モデルの必須フィールドを満たさない場合、エラーとして処理します。**
        * **GitHub 操作 (UseCase 経由、`adapters/github_client.py` を使用):**
            * **リポジトリ作成/確認 (`CreateRepositoryUseCase`):** プライベートリポジトリを `githubkit` で作成します (冪等)。Owner 省略時は認証ユーザー (`get_authenticated`) を Owner とします。
            * **ラベル作成/確認 (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.create_label`):** `ParsedRequirementData` 内の全ユニークラベルに対し、存在しなければ作成します (冪等)。色は GitHub デフォルトです。エラー発生時も処理継続し結果に記録します。
            * **マイルストーン作成/確認 (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.create_milestone`):** `ParsedRequirementData` 内で指定された**全ての**ユニークなマイルストーン名に対し、存在しなければ作成します (冪等)。エラー発生時も処理継続し結果に記録します。
            * **担当者有効性検証 (新規):** (`CreateIssuesUseCase` または `GitHubAppClient` 内) AI が抽出した各担当者名について、GitHub API を使用してユーザーの存在とリポジトリへのアクセス権限（コラボレーターであるかなど）を**事前に**検証する。検証に失敗した担当者はリストから除外し、ログに記録する。
            * **Issue 作成/設定 (`CreateIssuesUseCase` -> `GitHubAppClient.create_issue`):** `ParsedRequirementData` 内の各 `IssueData` に基づき Issue を作成します。タイトル、本文 (抽出した各セクションを結合)、ラベル、その Issue に指定されたマイルストーンの ID (事前に解決しておく)、**上記で検証済みの有効な**担当者リストを設定します。同名タイトル (Open状態) の Issue が存在する場合はスキップします。API エラー発生時は Issue 単位で処理継続し結果に記録します。成功時に Issue URL と Node ID を取得します。
            * **プロジェクト検索 (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.find_project_v2_node_id`):** `--project` 指定時、オーナー名とプロジェクト名で Project (V2) の Node ID を GraphQL で検索します。
            * **プロジェクトへの Issue 追加 (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.add_item_to_project_v2`):** プロジェクト Node ID と作成された Issue の Node ID を使用し、GraphQL でプロジェクトにアイテムを追加します。エラー発生時もアイテム単位で処理継続し結果に記録します。
        * **ワークフロー制御 (`CreateGitHubResourcesUseCase`):** 上記 GitHub 操作の実行順序 (Repo -> Labels -> Milestones (複数) -> Project Search -> Issues -> Project Add) を制御します。リポジトリ作成などの致命的エラー発生時は処理を中断し例外を送出します。
    * **出力:**
        * 標準出力/標準エラー出力: ログレベルに応じた処理状況、エラーメッセージ (`logging`)。**エラーメッセージは、現時点では詳細な原因や対処法までは含めず、発生したエラーの種類と内容が分かるレベルとします。**
        * 整形済み結果レポート: 全体の処理結果サマリー (`CreateGitHubResourcesResult`) を `CliReporter` がログに出力します。部分的失敗（**検証失敗担当者情報含む**）もこのレポートに含まれます。
    * **実行形態:** Python CLI アプリケーション (`Typer`、`main.py` がエントリーポイント)。Docker コンテナでの実行を推奨します。
    * **認証:** GitHub PAT (Classic: `repo`, `project` スコープ / Fine-grained: 必要な権限セット)、選択された AI モデルの API キー。
* **対象範囲外（Out of Scope）:**
    * Web UI、GUI インストーラー。
    * Markdown 以外の入力形式 (JSON, CSV 等) のサポート。
    * 入力 Markdown ファイルの構文チェックや作成支援（テンプレート提供は行う）。
    * AI による担当者の**推測**や自動割り当てロジック。
    * GitHub Enterprise Server (GHES) など、github.com 以外の環境対応。
    * **APIエラー発生時の自動リトライ処理。**
    * 生成 AI モデルの Fine-tuning や独自モデル利用。
    * Issue 間の依存関係 (親子、先行/後続) の自動設定。
    * Pull Request やブランチの自動作成。
    * GitHub Projects (V2) の**新規作成**、ビューやカスタムフィールドの設定。
    * リポジトリ設定 (コラボレーター、ブランチ保護、Issue/PR テンプレート、**デフォルトルールセット適用**)。
    * Markdown ファイル全体で共通のデフォルトラベル・マイルストーン等を定義・利用する機能。
    * ラベル作成時の色や説明文の指定機能。
    * プロジェクトへのアイテム追加時にステータス等のフィールド値を設定する機能。
    * **Organization リポジトリへの明示的な対応（現時点ではユーザーリポジトリ前提）。**
    * **AI 解析結果の中間ファイル（JSON等）出力および編集・再実行機能。**

## 4. 主要なステークホルダーと役割

* **開発者 (主要ユーザー):** GitHub セットアップ作業の効率化を期待。ツールの日常的な利用者。提供されるテンプレートに基づき Markdown ファイルを作成・編集する。ツール実行結果のログを確認する。
* **プロジェクトマネージャー (PM):** プロジェクト管理の効率化・標準化を期待。入力 Markdown の記述ルール策定に関与。ツールの導入効果を測定する。
* **(DDD観点):**
    * **ドメイン知識:** GitHub のリポジトリ、Issue、ラベル、マイルストーン、プロジェクト (V2) の概念と操作、およびそれらを開発プロセスでどのように利用するかについての知識が重要です。この知識は開発者と PM が主に持ちます。AI 解析の精度向上には、推奨される Markdown 構造や Issue に含まれるべき情報の知識も必要です。
    * **ユビキタス言語形成:** 要件定義書内の用語集にある「要件定義ファイル」「解析」「登録」「冪等性」「スキップ」「PAT」「Node ID」「UseCase」「Adapter」「Dry Run」などを共通言語として使用します。GitHub の公式用語 (Repository, Issue, Label, Milestone, Project V2, Assignee, Node ID など) もそのまま利用します。AI 解析に関連する用語 (Parse, Title, Description, Label, Milestone, Assignee) も重要です。

## 5. ユースケース定義

* **UC-001: Markdown ファイルから GitHub リソースを一括登録する**
    * **アクター:** 開発者、プロジェクトマネージャー
    * **事前条件:**
        1.  Docker 実行環境が利用可能である (推奨)。
        2.  有効な GitHub PAT (`repo`, `project` スコープまたは同等の Fine-grained 権限) と、選択された AI モデルの API キーが環境変数または `.env` ファイルに設定されている。
        3.  処理対象の Markdown ファイルが存在し、読み取り可能である。
        4.  CLI で `--file` (Markdown パス) と `--repo` (リポジトリ名) が指定されている。
    * **事後条件:**
        1.  指定されたリポジトリが存在しない場合、プライベートリポジトリとして作成される。
        2.  Markdown から抽出された全てのユニークなラベルと全てのユニークなマイルストーンが、リポジトリに存在しない場合に作成される。
        3.  Markdown から抽出された各 Issue が、リポジトリに同名の Open な Issue が存在しない場合に作成される (タイトル、本文、ラベル、該当 Issue に指定されたマイルストーン、**事前に検証された有効な**担当者のみ含む)。**無効な担当者が指定されていた場合は、その担当者は設定されず、警告が記録される。**
        4.  `--project` が指定され、該当する Project (V2) が存在する場合、作成された Issue がそのプロジェクトにアイテムとして追加される。
        5.  処理結果 (作成/スキップ/失敗/**検証失敗担当者**/エラー詳細) がログおよび標準出力に表示される。
        6.  致命的エラーが発生した場合、処理は中断し、非ゼロの終了コードで終了する。
    * **基本フロー (概要):**
        1.  `main.py`: Typer が CLI 引数を解析・検証。
        2.  `main.py`: `load_settings()` で設定を読み込み、検証。ロガーを設定。
        3.  `main.py`: `read_markdown_file()` で指定された Markdown ファイルを読み込む。
        4.  `main.py`: `AIParser` を初期化し、`parse()` メソッドで Markdown を解析、`ParsedRequirementData` を取得。AI 解析結果の必須項目が不足している場合はエラー終了。
        5.  `main.py`: `GitHubAppClient`, `CreateRepositoryUseCase`, `CreateIssuesUseCase` をインスタンス化 (依存性注入)。
        6.  `main.py`: `CreateGitHubResourcesUseCase` をインスタンス化。
        7.  `main.py`: `CreateGitHubResourcesUseCase.execute()` を呼び出し、`parsed_data`, `repo_name_input`, `project_name`, `dry_run` フラグを渡す。
        8.  `CreateGitHubResourcesUseCase`: `_get_owner_repo()` でリポジトリの Owner と Name を解決 (必要なら `get_authenticated` を使用)。
        9.  `CreateGitHubResourcesUseCase`: Dry Run モードでない場合、以下の処理を実行。
        10. `CreateGitHubResourcesUseCase`: `CreateRepositoryUseCase.execute()` を呼び出し、リポジトリを作成/確認。
        11. `CreateGitHubResourcesUseCase`: `ParsedRequirementData` からユニークなラベル名を収集し、ループ内で `GitHubAppClient.create_label()` を呼び出し、作成/確認 (エラーは記録)。
        12. `CreateGitHubResourcesUseCase`: `ParsedRequirementData` 内の全ての Issue からユニークなマイルストーン名を収集し、ループ内で `GitHubAppClient.create_milestone()` を呼び出し、作成/確認 (エラーは記録)。成功したマイルストーン名とその ID のマッピングを保持する。
        13. `CreateGitHubResourcesUseCase`: `project_name` が指定されていれば、`GitHubAppClient.find_project_v2_node_id()` を呼び出し、プロジェクト Node ID を検索 (エラーは記録)。
        14. `CreateGitHubResourcesUseCase`: `CreateIssuesUseCase.execute()` を呼び出し、Issue を作成/スキップ (担当者検証エラー含む) し、結果を記録。この際、ステップ 12 で作成/確認したマイルストーン名とIDのマッピング情報を渡す。
        15. `CreateGitHubResourcesUseCase`: プロジェクト Node ID と作成された Issue の Node ID があれば、ループ内で `GitHubAppClient.add_item_to_project_v2()` を呼び出し、アイテムを追加 (エラーは記録)。
        16. `CreateGitHubResourcesUseCase`: 全ての処理結果をまとめた `CreateGitHubResourcesResult` オブジェクトを構築して返却 (複数のマイルストーン結果、検証失敗担当者情報等を含む)。
        17. `main.py`: 受け取った `CreateGitHubResourcesResult` を `CliReporter.display_create_github_resources_result()` に渡し、結果を表示。
    * **代替フロー（例外フロー）:**
        * 設定読み込み、ファイル読み込み、AI 解析 (必須項目不足含む)、リポジトリ名解決、リポジトリ作成/確認、**担当者検証** のいずれかで致命的エラーが発生した場合、UseCase または `main.py` が例外を送出し、`main.py` が捕捉してエラーメッセージを表示し、非ゼロコードで終了する。
        * ラベル作成、マイルストーン作成 (個別)、プロジェクト検索、Issue 作成 (個別)、プロジェクトへのアイテム追加 (個別) でAPIエラー等が発生した場合、処理は可能な限り続行され、エラー情報が最終結果に記録される。

## 6. ドメインモデル（初期案）
* **値オブジェクト (Value Object):**
    * `IssueData`: AI によって解析された単一 Issue の情報の不変なスナップショットです。タイトル、説明、タスクリスト、関連要件リスト、関連 Issue リスト、受け入れ基準リスト、ラベルリスト、**その Issue に対応する**マイルストーン名、担当者リストを持ちます。`Pydantic BaseModel` で実装されます。
* **エンティティ (Entity):**
    * 現状、明確なドメインエンティティは少ないです。GitHub 上のリソース (リポジトリ、Issue、ラベル、マイルストーン) は外部システムのエンティティであり、本ツール内では主に ID や名前で参照されます。強いて言えば、ツールの一連の実行結果を表す `CreateGitHubResourcesResult` が、実行コンテキストにおける情報保持の役割を持ちます。
* **集約 (Aggregate):**
    * `ParsedRequirementData`: Markdown ファイル全体から解析された `IssueData` のリストを保持する集約です。ファイル単位の解析結果全体を表すルートです。`Pydantic BaseModel` で実装されます。
    * `CreateIssuesResult`: Issue 作成処理の結果（成功、スキップ、失敗、**検証失敗担当者情報**）を集約します。`Pydantic BaseModel` で実装されます。**(注: このモデルに検証失敗担当者情報を追加するフィールド定義が必要)**
    * `CreateGitHubResourcesResult`: ツール実行全体のワークフロー結果（リポジトリ情報、ラベル結果、複数のマイルストーン結果、Issue 結果、プロジェクト連携結果、致命的エラー）を集約するルートです。`Pydantic BaseModel` で実装されます。
* **ドメインイベント (Domain Event):**
    * 現状、明示的なドメインイベントは実装されていません。将来的に、処理の各段階（例: `IssueCreated`, `RepositoryCreationFailed`）をイベントとして発行し、Observer パターンなどで通知や追加処理を行うアーキテクチャも検討可能です。
* **ドメイン例外 (Domain Exception):** (`domain/exceptions.py`)
    * `GitHubClientError` (基底)
    * `GitHubAuthenticationError`
    * `GitHubRateLimitError`
    * `GitHubResourceNotFoundError`
    * `GitHubValidationError`
    * `AiParserError`
    これらは外部システムとのインタラクションにおけるドメイン知識（エラーの種類）を表現します。
* **ユビキタス言語候補 (再掲):** 要件定義ファイル (Markdown), 解析 (Parse), 登録 (Create/Ensure), 冪等性 (Idempotency), スキップ (Skip), リポジトリ (Repository), Issue, ラベル (Label), マイルストーン (Milestone), 担当者 (Assignee), プロジェクト (Project V2), アイテム (Item), PAT, APIキー, CLI, Dry Run, UseCase, Adapter, 結果 (Result), エラー (Error), 成功 (Success), 失敗 (Failed), 検証失敗担当者 (Validation Failed Assignee)。

## 7. 機能要件
* **(TDD観点):** 各要件は入力、処理、期待される出力/状態変化が明確であり、テストケースを作成可能にします。
* **FR-001:** 指定された Markdown ファイル (`--file`) の内容を UTF-8 で読み込むこと。
    * 入力: ファイルパス (Path オブジェクト)
    * 処理: ファイルを開き、内容を文字列として読み取る。
    * 出力: ファイル内容の文字列。
    * 例外: `FileNotFoundError`, `PermissionError`, `UnicodeDecodeError`, `IOError` を適切に送出すること (`infrastructure/file_reader.py`)。
* **FR-002:** 設定された AI モデル (OpenAI または Gemini) を使用して、Markdown テキストから Issue 情報を抽出し、`ParsedRequirementData` オブジェクトに構造化すること (`adapters/ai_parser.py`)。Pydantic モデルでの必須項目チェックを含む。
    * 入力: Markdown テキスト文字列。
    * 処理: プロンプトテンプレートと AI API を使用して解析。抽出項目は `IssueData` モデルのフィールドに対応。
    * 出力: `ParsedRequirementData` オブジェクト。
    * 例外: API キー不備、API 通信エラー、出力形式パースエラー等の場合に `AiParserError` を送出。
* **FR-003:** 指定されたリポジトリ名 (`--repo`) に基づき、GitHub 上に**プライベート**リポジトリを作成または確認すること (`CreateRepositoryUseCase`)。Owner 省略時の挙動、冪等性考慮を含む。
    * 入力: リポジトリ名文字列 (`owner/repo` または `repo`)。
    * 処理:
        * `owner/repo` 形式の場合はそのまま使用。
        * `repo` 形式の場合は、認証ユーザーのログイン名を Owner として使用 (`get_authenticated`)。
        * `githubkit` を使用してリポジトリ作成 API (`create_for_authenticated_user`) を呼び出す (`private=True`, `auto_init=True`)。
        * 既に同名リポジトリが存在する場合 (API が 422 エラー、メッセージに "already exists" を含む場合) は `GitHubValidationError` を送出。
    * 出力: 作成/確認されたリポジトリの URL。
    * 例外: `ValueError` (リポジトリ名形式不正)、`GitHubAuthenticationError`, `GitHubRateLimitError`, `GitHubValidationError`, `GitHubClientError`。
* **FR-004:** `ParsedRequirementData` 内の各 `IssueData` に基づき、GitHub Issue を作成すること (`CreateIssuesUseCase`)。同名 Open Issue のスキップ、ラベル、各 Issue に指定されたマイルストーンの設定を含む。**Issue 作成前に、担当者リストの各ユーザーについて有効性を検証し、有効な担当者のみを Issue に設定すること。** 個別エラー発生時は処理継続。
    * 入力: `ParsedRequirementData` オブジェクト、Owner 名、Repo 名、マイルストーン名とIDのマッピング情報。
    * 処理:
        * 各 `IssueData` について、`GitHubAppClient.find_issue_by_title()` で同名 Open Issue の存在を確認。
        * 存在しない場合:
            * **担当者検証:** `IssueData.assignees` に含まれる各担当者について、`GitHubAppClient` 等を使用して有効性を検証する (例: `GET /users/{username}` またはコラボレーター判定 API)。
            * **有効な担当者リスト作成:** 検証に成功した担当者のみを含むリストを作成する。検証に失敗した担当者はログに記録する。
            * `GitHubAppClient.create_issue()` を呼び出す。
                * `title`: `IssueData.title`
                * `body`: `IssueData.description`, `tasks` 等を結合した本文。
                * `labels`: `IssueData.labels` (リスト)
                * `milestone`: `IssueData.milestone` に指定されたマイルストーン名に対応する数値 ID をマッピング情報から取得して設定。見つからない/エラーの場合は設定しない。
                * `assignees`: **上記で作成した有効な担当者リスト**を設定。
        * **API エラーが発生した場合:** Issue 作成失敗としてエラーを記録する。
        * 存在する場合はスキップ。
    * 出力: `CreateIssuesResult` オブジェクト (作成された Issue の URL/Node ID、スキップされたタイトル、失敗したタイトルとエラーリスト、**検証失敗担当者情報リスト**)。**(注: CreateIssuesResult モデルに検証失敗担当者情報リストのフィールド追加が必要)**
    * 例外: Issue 単位のエラーは `CreateIssuesResult` に記録し、可能な限り処理を継続。
* **FR-005:** `ParsedRequirementData` 内の全ユニークラベルについて、GitHub ラベルを作成または確認すること (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.create_label`)。冪等性考慮。個別エラー発生時は処理継続。
    * 入力: Owner 名、Repo 名、ラベル名。
    * 処理: `get_label()` で存在確認し、なければ `create_label()` を呼び出す (色は GitHub デフォルト)。
    * 出力: 作成された場合は True、既存の場合は False。
    * 例外: API エラー (`GitHubClientError` 等) を捕捉し、`CreateGitHubResourcesResult` に記録。
* **FR-006:** `ParsedRequirementData` 内の**全ての**ユニークなマイルストーン名について、GitHub マイルストーンを作成または確認すること (`CreateGitHubResourcesUseCase` -> `GitHubAppClient.create_milestone`)。冪等性考慮。個別エラー発生時は処理継続。
    * 入力: Owner 名、Repo 名、マイルストーン名。
    * 処理: `find_milestone_by_title()` で存在確認 (Open状態) し、なければ `create_milestone()` を呼び出す。
    * 出力: 作成/確認されたマイルストーンの ID **と名前のペア**。
    * 例外: API エラー (`GitHubClientError` 等) を捕捉し、`CreateGitHubResourcesResult` に記録。
* **FR-007:** Issue 作成時に、`IssueData.assignees` に含まれる GitHub ユーザー名を**事前に検証し、有効なユーザーのみを**担当者として設定すること。
    * 入力: Owner 名、Repo 名、担当者候補リスト。
    * 処理: 各担当者候補について GitHub API を使用して有効性を検証する。有効な担当者のみを含むリストを Issue ペイロードの `assignees` に設定して `githubkit` の `create_issue` API を呼び出す。
    * 出力: Issue オブジェクト (API レスポンス)。
* **FR-008:** `--project` が指定された場合、該当する GitHub Project (V2) を検索し、作成された Issue をアイテムとして追加すること (`CreateGitHubResourcesUseCase`)。個別エラー発生時は処理継続。
    * 入力: Owner 名、プロジェクト名、プロジェクト Node ID、Issue Node ID。
    * 処理:
        * `GitHubAppClient.find_project_v2_node_id()` でプロジェクト Node ID を検索 (GraphQL)。
        * プロジェクトが見つかり、Issue が作成された場合、`GitHubAppClient.add_item_to_project_v2()` を呼び出す (GraphQL)。
    * 出力: プロジェクト Node ID、追加されたアイテムの ID (またはエラー情報)。
    * 例外: プロジェクト検索エラー、アイテム追加エラー (`GitHubClientError` 等) を捕捉し、`CreateGitHubResourcesResult` に記録。
* **FR-009:** `--dry-run` オプションが指定された場合、GitHub への書き込み操作 (リポジトリ作成、ラベル作成、マイルストーン作成、Issue 作成、アイテム追加) を行わず、実行されるであろう操作のログを出力すること。
    * 入力: `--dry-run` フラグ。
    * 処理: `CreateGitHubResourcesUseCase` 内でフラグをチェックし、書き込みを伴う UseCase や Client メソッドの呼び出しをスキップ。シミュレーション結果を `CreateGitHubResourcesResult` に設定。
    * 出力: Dry Run モードである旨のログ、実行されるはずだった操作のログ、シミュレーション結果を含む `CreateGitHubResourcesResult`。

## 8. 非機能要件

* **性能:**
    * 一般的な Markdown ファイル (例: 10 Issue 程度) の処理は、ネットワーク環境に依存するが、AI 解析、**担当者検証**を含め 1-2 分以内に完了すること (目標)。(**担当者検証による API コール増加を考慮**)
    * **(TDD/Clean Architecture観点):** 外部 API 呼び出しはモック可能であるため、コアロジックの単体テストは高速に実行できます。`githubkit` 等のライブラリの性能に依存する部分は結合テストや実測で確認します。
* **可用性:**
    * CLI ツールであるため、ユーザーの実行環境と外部 API (GitHub, AI) の可用性に依存します。ツール自体の稼働率は問いません。
    * GitHub API や AI API の一時的な障害発生時、エラーメッセージを出力して**処理を停止します。リトライ機構は現時点では実装しません。**
* **セキュリティ:**
    * GitHub PAT および AI API キーは、`.env` ファイルまたは環境変数で管理し、コード中にハードコードしません (`pydantic-settings`, `SecretStr` を使用)。
    * `.env` ファイルは `.gitignore` に追加し、リポジトリにコミットしません。
    * GitHub PAT には必要最小限のスコープ (`repo`, `project`) または権限を付与することを推奨します。**GitHub Apps への移行は現時点では検討しません。**
* **保守性/拡張性 (Clean Architecture/DDD観点):**
    * レイヤー間の依存方向は UI -> UseCase -> Domain <- Adapters <- Infrastructure とし、依存性逆転の原則を適用します。
    * Domain 層はフレームワークや外部ライブラリへの依存を最小限にします (現状 `Pydantic` のみ)。
    * UseCase は具体的なインフラ詳細 (ファイル I/O, API クライアント実装) から分離します。
    * 新しい AI モデルや GitHub クライアントライブラリへの変更は、対応する Adapter の修正に限定されるようにします。
    * 新しい機能 (例: PR作成) は、新しい UseCase や必要に応じて Domain モデル、Adapter を追加することで実現できるようにします。
    * **将来的なリトライ処理の導入を考慮し、API クライアント層 (`GitHubAppClient`) での例外ハンドリングを明確に分離しておきます。**
    * **将来的な中間生成物（JSON等）の操作機能追加を考慮し、AI 解析処理 (`AIParser`) と GitHub 登録処理 (`CreateGitHubResourcesUseCase`) が明確に分離されていることを維持します。**
    * **将来的なリポジトリ可視性（Public/Private）設定の追加や、デフォルトルールセット適用のための拡張ポイントをリポジトリ作成 UseCase 周辺に考慮しておきます（インターフェースの柔軟性など）。**
* **テスト容易性 (TDD観点):**
    * 各レイヤー、特に UseCase と Domain は単体テスト可能であること。外部依存 (API, ファイルシステム, AI) はモック (`unittest.mock`) を使用してテストします。
    * `pytest` をテストフレームワークとして使用し、カバレッジ計測 (`pytest-cov`) を行います。目標カバレッジ 80% を CI で維持します。
    * `CliReporter` による出力もテスト可能であること (`caplog` フィクスチャ等を使用)。
    * CLI の引数解析や基本的な動作は `Typer.testing.CliRunner` でテストします。
* **UI/UX:**
    * CLI のオプション名 (`--file`, `--repo` 等) とヘルプメッセージは分かりやすいものとします (`Typer` の機能を利用)。
    * 処理の進捗状況（例: 何件目の Issue を処理中かなど）と最終結果（**検証に失敗した担当者がいる場合はその情報も含む**）は、適切なログレベルとフォーマットで表示します (`logging`, `CliReporter`)。エラー発生時は原因と対処法が推測できる情報を提供します。
* **その他:**
    * **(AI 解析の不確実性):** AI による Markdown 解析結果は常に正しいとは限らないため、ユーザーは生成された Issue 等の内容を確認・修正する必要がある可能性があることを明記します。
    * **(担当者検証の限界):** 担当者検証ではユーザー存在は確認できるが、対象プライベートリポジトリへのアクセス権限までを正確に判定できない可能性がある点に留意する。(注: 実装方法による)

## 9. 受け入れ基準（Acceptance Criteria）

* **(TDD観点):** 各基準は具体的なテストシナリオに対応し、自動テストで検証可能であること。
* **AC-Core-Flow (UC-001 基本フロー):** `python -m github_automation_tool --file <valid_markdown> --repo owner/new-repo` を実行すると、GitHub 上に `owner/new-repo` (プライベート) が作成され、Markdown 内の Issue、ラベル、**言及された全ての**マイルストーンが冪等に作成され、**各 Issue に正しいマイルストーンが設定される**こと。成功を示すログが出力されること。
* **AC-Project-Link (UC-001 プロジェクト連携):**
    * `--project "Existing Project"` を付けて実行し、"Existing Project" が存在する場合、作成された Issue がそのプロジェクトにアイテムとして追加され、成功ログが出力されること。
    * `--project "Non Existing Project"` を付けて実行した場合、プロジェクトが見つからない旨の警告ログが出力され、アイテム追加処理は行われず、他の処理は正常に完了すること。
* **AC-Dry-Run (FR-009):**
    * `--dry-run` を付けて実行した場合、GitHub 上に変更が加えられず、「Dry run mode enabled」および実行されるであろう操作を示すログが出力されること。
* **AC-Owner-Infer (FR-003):**
    * `--repo repo-name-only` を付けて実行した場合、認証ユーザー (`test-auth-user`) の下に `test-auth-user/repo-name-only` リポジトリが作成されること。
* **AC-Error-Handling (NFR-Err-01, NFR-Err-02):**
    * GitHub PAT が無効な状態で実行すると、認証エラーを示すメッセージが表示され、非ゼロコードで終了すること。
    * `--file` に存在しないファイルを指定すると、ファイルが見つからない旨のエラーメッセージが表示され、非ゼロコードで終了すること。
    * ラベル作成 API や個別のマイルストーン作成 API、**担当者検証 API** が一時的に失敗しても、エラーがログに記録され、Issue 作成などの後続処理は可能な限り実行されること。最終結果レポートに失敗情報が含まれること。
* **AC-Assignee-Validation-Mixed (新規):** 有効な担当者と無効な担当者が混在する Issue を処理した場合、Issue は有効な担当者のみが設定された状態で作成され、無効な担当者が検証に失敗した旨の警告ログが出力されること。
* **AC-Assignee-Validation-AllInvalid (新規):** 全ての担当者が無効な Issue を処理した場合、Issue は担当者が設定されない状態で作成され、無効な担当者が検証に失敗した旨の警告ログが出力されること。
* **AC-Assignee-Validation-ApiError (新規):** 担当者検証のための GitHub API 呼び出しが失敗した場合（例: レート制限）、該当 Issue の担当者設定は行われず、エラーがログに記録されること（Issue 作成自体は試行される）。
* **AC-Tests-Pass (NFR-Test-01, NFR-Test-02):**
    * 開発環境で `pytest` コマンドを実行すると、全てのユニットテスト (現時点で 145 件 **+ 新機能分**) が成功すること。
    * `pytest --cov` によるカバレッジ計測結果が 80% 以上であること。
* **AC-AI-Switch (NFR-AI-01):**
    * 環境変数 `AI_MODEL=gemini` (かつ `GEMINI_API_KEY` が有効) を設定して実行すると、Gemini モデルが使用されて処理が正常に完了すること (ログ等で確認)。デフォルト (または `AI_MODEL=openai`) では OpenAI モデルが使用されること。

## 10. 用語集

* **(DDD観点):** プロジェクト固有の概念と GitHub/AI 関連の技術用語を明確に定義し、共通理解を促進します。
* **要件定義ファイル (Requirement File):** 本ツールが入力として受け取る、GitHub リソース情報を特定の書式（推奨）で記述した Markdown テキストファイル。
* **生成AI (Generative AI):** テキスト解析に利用する AI モデル。OpenAI の GPT モデルまたは Google の Gemini モデルを指す。
* **解析 (Parse):** 生成 AI が Markdown テキストの内容を解釈し、Issue タイトル、説明、ラベル、マイルストーン、担当者などの情報を抽出し、構造化データ (`ParsedRequirementData`) を生成するプロセス。
* **登録 (Register / Create / Ensure):** AI 解析結果や CLI 引数を元に、GitHub API を通じて実際に GitHub 上にリソース (リポジトリ、ラベル、マイルストーン、Issue、プロジェクトアイテム) を作成・設定するプロセス。「Ensure」は冪等性を意識した表現。
* **冪等性 (Idempotency):** ある操作を 1 回実行しても複数回実行しても、システムの状態が同じになるという性質。リポジトリ作成、ラベル作成、マイルストーン作成、Issue 作成 (タイトル重複回避) で考慮される。
* **スキップ (Skip):** 冪等性担保のため、既に存在するリソース (例: 同名タイトル の Open Issue) の作成処理を実行しないこと。
* **PAT (Personal Access Token):** GitHub API の認証に使用する個人アクセストークン。Classic PAT の場合は `repo` および `project` スコープが必要。Fine-grained PAT の場合は、必要な権限を個別に設定する（詳細は README 等を参照）。
* **APIキー (API Key):** 生成 AI (OpenAI, Gemini) の API 認証に使用するキー。
* **CLI (Command Line Interface):** 本ツールが提供するコマンドラインベースのユーザーインターフェース (`Typer` で実装)。
* **プロジェクトV2 (Project V2):** GitHub の提供する新しいプロジェクト管理機能。Issue や PR をアイテムとして追加できる。
* **Node ID:** GitHub GraphQL API でオブジェクトを一意に識別するためのグローバル ID。
* **UseCase (Interactor):** アプリケーション固有のビジネスロジックや一連の処理フロー (ワークフロー) を実装するコンポーネント (例: `CreateGitHubResourcesUseCase`)。ドメイン層やインフラ層に直接依存せず、インターフェース (抽象) に依存する。
* **Adapter:** UseCase 層と外部要素 (UI, DB, 外部 API クライアント) を接続するコンポーネント。依存性の方向を制御する役割を持つ (例: `GitHubAppClient`, `AIParser`, `CliReporter`)。
* **Dry Run:** 実際には GitHub 上の状態を変更せず、実行されるであろう操作をシミュレートし、ログに出力するモード (`--dry-run`)。
* **担当者検証 (Assignee Validation):** Issue 作成前に、指定された担当者名が GitHub 上で有効なユーザーであり、かつ対象リポジトリにアクセス可能かを確認するプロセス。

## 11. 制約条件・前提条件
* **開発言語:** Python 3.10 以上 (テスト環境: Python 3.13.3)。
* **実行環境:** Docker コンテナ (Linux ベース) での実行を強く推奨。ローカル実行の場合も Python 3.10+ および依存ライブラリのインストールが必要。インターネット接続必須。
* **外部 API 依存:**
    * GitHub API (REST v3, GraphQL v4): API の仕様変更、レート制限、障害発生の影響を受ける可能性がある。**担当者検証のための API コールが増加するため、レート制限に注意が必要。**
    * OpenAI API または Google Generative AI API: API の仕様変更、利用料金、利用制限、障害発生の影響を受ける可能性がある。
* **主要ライブラリ依存:** `typer`, `pydantic`, `pydantic-settings`, `githubkit`, `openai` (または `langchain-openai`), `google-generativeai` (または `langchain-google-genai`), `python-dotenv`, `pytest`, `pytest-cov`, `unittest.mock` など。これらのライブラリのバージョンアップや互換性の問題に注意が必要。
* **認証:** 有効な GitHub PAT (**必要なスコープまたは権限を持つ Classic PAT または Fine-grained PAT**) と、選択した AI モデルに対応する有効な API キーが、環境変数または `.env` ファイル経由で**実行環境に**正しく設定されていること。
* **入力フォーマット:** 入力は UTF-8 エンコードされた Markdown ファイルであること。AI が情報を正確に抽出しやすいように、推奨される書式 (例: `**Title:**`, `**Labels:**`, `**Milestone:**` などのセクション構造) に従うことが望ましい。書式が大きく異なると、解析精度が低下する可能性がある。
* **AI 解析の限界:** 生成 AI による解析結果は 100% の精度を保証するものではない。特に曖昧な記述や複雑な構造の Markdown に対しては、誤った抽出や情報の欠落が発生する可能性がある。ユーザーによる**最終確認と必要に応じた手動修正**が前提となる。
* **利用者の前提:** 本ツールは、GitHub アカウントを所有し、自身のアカウントのリポジトリに対して操作を行う開発者または PM が利用することを前提とする。**他者のアカウントや Organization のリポジトリを操作することは想定していない。** **Markdown 内に記述する担当者名は、可能な限り対象リポジトリで有効なユーザー名を指定することが推奨される（ツールによる事前チェックは行われるが、権限チェックの限界等により完全ではない可能性がある）。**