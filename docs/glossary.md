# 用語集 (Glossary)

このドキュメントは、「github-auto-setup」プロジェクトで使用される主要な用語とその定義をまとめたものです。

---

## A

**Adapter (アダプター層)**
:   クリーンアーキテクチャにおける層の一つ。コアロジックと外部システム（GitHub API, AIサービス API, ファイルシステムなど）または特定技術（CLI, Webフレームワーク）との間で情報をやり取りする責務を持つコンポーネント群。

**AI Parser (`AIParser`)**
:   初期パーサーによって分割されたIssueブロック群（およびファイル全体のコンテキスト）をAI（OpenAI/Gemini）に入力し、構造化データモデル `ParsedSourceFileContent` を生成するコンポーネント。キーの揺らぎ吸収や意味解釈を担う。

**Application Service Layer (アプリケーションサービス層 - Web UI向け)**
:   (検討中) DjangoビューとコアロジックのUseCase間のファサードとして機能し、UI固有の調整や複数のUseCase呼び出しのオーケストレーションを行う層。

**Assignee Validator (担当者検証アダプター)**
:   GitHub APIを利用して、Issueに割り当てる担当者の有効性（リポジトリのコラボレーターであるかなど）を検証するアダプター。

## AI Parser
本システムの中核機能の一つ。ユーザーが提供するIssue情報ファイル（Markdown, YAML, JSON）の内容全体を分析し、以下の2種類の主要なルールを動的に推論・生成する。
1.  **Issue区切りルール (主に先頭キー/開始パターンの推論):** ファイル内で何がIssueブロック/レコードの開始を示すか、その「先頭キー/開始パターン」をAIが推論する。AIによる推論が困難な場合は、フォールバックとして一般的な区切りパターン（Markdownの水平線やヘッダーレベル、YAML/JSONのリスト構造など）や設定ファイルで指定されたルールが適用されることもある。
2.  **キーマッピングルール:** 推論された各Issueブロック/レコード内で、入力ファイル中のどのキーや記述が、本システムの標準的なIssueデータモデル（`IssueData`）のどのフィールドに対応するか、その対応関係（例: キーとフィールド名の辞書）。
これらの推論されたルール（またはフォールバック/設定ルール）に基づき、後続のルールベース処理でファイルがIssueブロックに分割され、各ブロックが`IssueData`オブジェクトにマッピングされる。

## Issue区切りルール (Delimiter Rule / Segmentation Rule)
AIパーサーによって主に推論される、またはフォールバック/設定によって決定される、個々のIssue情報の開始点や境界を特定するためのルール。AIは特に、ファイル内で共通して使われる「先頭キー/開始パターン」を推論する。その他のパターン（Markdownのヘッダーレベル、水平線、YAML/JSONのリスト構造など）もルールとして扱われる。

## キーマッピングルール (Key Mapping Rule)
AIパーサーによって、Issue情報ファイル内の各Issueブロック/レコードから推論される、入力ファイル中のキー（または記述パターン）と、本システムの標準Issueデータモデル（`IssueData`）のフィールド名との対応関係を示すルール。例：「入力ファイル中のキー `件名` は `IssueData.title` に対応する」など。

## ParsedSourceFileContent
AIパーサーによる解析結果全体を格納するドメインモデル。以下の主要な情報を含む。
- `issues`: 解析・マッピングされた `IssueData` オブジェクトのリスト。
- `file_meta`: （オプション）ファイル全体から抽出されたメタ情報（例: デフォルトのプロジェクト名など）。

## IssueData
個々のIssue情報を格納する標準的なドメインモデル。`title`, `description`, `labels`, `milestone`, `assignees` などのフィールドを持つ。

## ルールベース分割処理 (Rule-based Splitter)
AIパーサーが推論した「Issue区切りルール（先頭キー/開始パターン）」に基づき、ファイルコンテンツをIssueブロックのリスト（`IntermediateParsingResult`）に分割する処理コンポーネント。

## ルールベースマッピング処理 (Rule-based Mapper)
AIパーサーが推論した「キーマッピングルール」と、分割されたIssueブロックリストに基づき、各ブロックを`IssueData`オブジェクトに変換する処理コンポーネント。この際、ラベル・マイルストーン以外のフィールドのマッピングを主に行う。

## ラベル・マイルストーン正規化 (Label/Milestone Normalization)
ルールベースマッピング処理でIssueブロックから抽出されたラベルやマイルストーンらしき記述を、`docs/github_setup_defaults.yml` に定義された正規の名称と照合し、統一された形式に変換して `IssueData` に設定する処理。

## C

**CLI (Command Line Interface)**
:   Typerで構築された、コマンドライン経由で操作可能なユーザーインターフェース。

**Core Logic (`core_logic`)**
:   UI技術から独立した、本アプリケーションの中核的なビジネスロジックとドメイン知識を実装したPythonパッケージ。Domain Models, Use Cases, Adapters, Infrastructureの各層を含む。

## D

**Domain Model (ドメインモデル)**
:   システムのビジネスロジックとルールを表現するオブジェクト。`IssueData` や `ParsedSourceFileContent` などが含まれる。

**Dry Runモード**
:   実際にGitHubに変更を加えず、実行される予定の操作内容をシミュレートする実行モード。Web UIとCLIの両方でサポートされる。

## G

**GitHub API Client (GitHub APIクライアント)**
:   `githubkit` ライブラリを基盤とし、GitHubのREST APIおよびGraphQL APIと通信するためのアダプター群 (`GitHubRestClient`, `GitHubGraphQLClient`)。

## I

**Infrastructure (インフラストラクチャ層)**
:   設定ファイルの読み込み、ファイルシステムへのアクセスなど、低レベルな技術的詳細を扱う層。

**Initial Parser (初期パーサー)**
:   ファイル形式（Markdown, YAML, JSON）に応じて、Issue情報ファイルの内容をIssue単位のブロック（文字列または辞書）に分割するコンポーネント。`AIParser`への入力を作成する。

**Issue Data (`IssueData`)**
:   AIパーサーまたは初期パーサーによって解釈された、単一のGitHub Issueに相当する情報を保持するPydanticモデル。タイトル、説明、ラベル、マイルストーン、担当者などの属性を含む。

**Issue情報ファイル**
:   `.md` (Markdown), `.yml` (YAML), `.json` (JSON) 形式で記述された、Issueの元となるデータを含む単一のファイル。

## L

**Local File Save (ローカルファイル保存)**
:   解析されたIssue情報を、個別のYAMLファイルとしてローカルファイルシステムに保存する機能。目次となる`index.html`も生成される。

## P

**ParsedSourceFileContent**
:   単一の入力ファイルから、初期パーサーおよびAIパーサーによって解析・マッピングされた情報全体を保持するPydanticモデル。主な内容として`IssueData`のリストと、ファイル全体から抽出されたメタ情報（例: デフォルトのプロジェクト名、共通ラベル、共通マイルストーンなど）を含む。旧`ParsedRequirementData`。

**PAT (Personal Access Token)**
:   GitHub APIと安全に通信するために必要な個人アクセストークン。`repo` および `project` スコープが必要。

**Presentation Layer (プレゼンテーション層)**
:   ユーザーとの直接的なインターフェースを提供する層。Web UI (Django) と CLI (Typer) が該当する。

## U

**UseCase (ユースケース)**
:   コアロジック内で特定の業務フロー（例: GitHubリソース一括作成、Issue作成など）を実現するコンポーネント。アプリケーションの主要な機能単位。

## W

**Web UI (ウェブユーザーインターフェース)**
:   DjangoとBootstrap5で構築された、ブラウザ経由で操作可能なユーザーインターフェース。

---