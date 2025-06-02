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