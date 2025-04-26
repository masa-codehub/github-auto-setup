# サンプルプロジェクト: 新しいウィジェット管理システム

## ステップ1: マイルストーンの提案

このプロジェクトのマイルストーンは以下の通りです。

1.  **`基盤構築完了`**: 認証、基本データモデル、APIクライアントのセットアップ。
2.  **`MVPリリース: Repo/Issue作成`**: ウィジェットの登録・一覧表示機能。
3.  **`v1.0リリース: 基本機能完了`**: ウィジェットの更新・削除、検索機能の追加。
4.  **`v1.1リリース: 安定化・改善`**: パフォーマンスチューニングとUI改善。

## ステップ2: ラベルの提案

プロジェクトで使用するラベルの例です。

- **種類 (Type):** `feature`, `bug`, `chore`, `refactoring`, `test`, `documentation`
- **レイヤー (Layer):** `domain`, `usecase`, `adapter-ui`, `adapter-db`, `adapter-external`, `infrastructure`
- **機能 (Feature):** `ウィジェット管理`, `認証`, `検索`
- **優先度 (Priority):** `priority: high`, `priority: medium`, `priority: low`
- **その他:** `TDD`, `Clean-Architecture`, `needs-discussion`

## ステップ3: GitHub Issuesへのタスク分解

---
**Title:** [Feature] ウィジェット登録機能の実装 (API)

**Description:**
新しいウィジェットをシステムに登録するためのバックエンドAPIエンドポイントを実装する。
ウィジェット名と説明を受け取り、データベースに保存する。

**タスク:**
- [ ] `Widget` ドメインエンティティ定義 (`domain` レイヤー)
- [ ] `WidgetRepository` インターフェース定義 (`usecase` レイヤー)
- [ ] `CreateWidgetUseCase` 実装 (`usecase` レイヤー)
- [ ] `WidgetRepository` のデータベース実装 (`adapter-db` レイヤー)
- [ ] API エンドポイント `/widgets` (POST) の実装 (`adapter-ui` レイヤー相当、ここではAPIアダプタ)
- [ ] （TDD）`Widget` エンティティの単体テスト
- [ ] （TDD）`CreateWidgetUseCase` の単体テスト
- [ ] （TDD）リポジトリ実装の結合テスト

**受け入れ基準:**
- POST /widgets リクエストでウィジェット名と説明を送信すると、201 Created が返却されること。
- 不正なリクエスト（名前が空など）の場合、400 Bad Request が返却されること。
- データベースにウィジェット情報が正しく保存されていること。
- テストカバレッジが 85% 以上であること。

**関連要件:** UC-Widget-Create, FR-Widget-001

**Milestone:** `MVPリリース: Repo/Issue作成`
**Labels:** `feature`, `usecase`, `domain`, `adapter-db`, `adapter-ui`, `test`, `ウィジェット管理`, `priority: high`, `TDD`
**Assignee:** @dev-backend
---
**Title:** [Refactoring] 認証モジュールのリファクタリング

**Description:**
現在の認証モジュールは可読性が低く、テストが難しい箇所があるためリファクタリングを行う。
特にトークン検証ロジックを独立したクラスに切り出す。

**タスク:**
- [ ] 現状の認証フローとコードを分析する
- [ ] トークン検証ロジックを `TokenValidator` クラスとして分離する (`infrastructure` レイヤー)
- [ ] 認証ミドルウェア/ハンドラから `TokenValidator` を利用するように修正する (`adapter-ui` / `infrastructure`)
- [ ] （TDD）`TokenValidator` に対する単体テストを作成する
- [ ] 既存の認証関連テストを修正・更新する

**受け入れ基準:**
- リファクタリング後も、既存の認証機能（ログイン、トークン検証）が正常に動作すること。
- `TokenValidator` のテストカバレッジが 90% 以上であること。
- コードの循環的複雑度が改善されていること。

**関連要件:** NFR-Maintainability

**Milestone:** `基盤構築完了`
**Labels:** `refactoring`, `infrastructure`, `auth`, `test`, `priority: medium`, `TDD`
**Assignee:** @dev-senior, @dev-backend
---
**Title:** [Documentation] API仕様書 (ウィジェット登録) の作成

**Description:**
実装されたウィジェット登録API (`POST /widgets`) の仕様を OpenAPI (Swagger) 形式で記述する。

**タスク:**
- [ ] リクエストボディのスキーマ定義
- [ ] 正常系レスポンス (201) のスキーマ定義
- [ ] エラーレスポンス (400) のスキーマ定義
- [ ] エンドポイントのパス、メソッド、パラメータ、説明を記述
- [ ] 作成した仕様書をリポジトリに追加 (`docs/api/widgets.yaml`)

**受け入れ基準:**
- OpenAPI 仕様書が作成され、Swagger Editor 等でバリデーションエラーが出ないこと。
- 仕様書の内容が実際のAPI実装と一致していること。
- チームメンバーによるレビューが完了していること。

**関連要件:** FR-Widget-001

**Milestone:** `MVPリリース: Repo/Issue作成`
**Labels:** `documentation`, `ウィジェット管理`, `priority: low`
---