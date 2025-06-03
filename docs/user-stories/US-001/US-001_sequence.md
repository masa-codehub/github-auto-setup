# US-001: Web UIでのIssueファイルのアップロード、AIによる区切り・キーマッピングルール推論と解析、一覧表示 - シーケンス図

このドキュメントは、ユーザーストーリー US-001 の主要なコンポーネント間のインタラクションを時系列で図示します。

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant StaticFrontend as 静的フロントエンド (JS)
    participant BackendAPI as バックエンドAPI (Django/DRF)
    participant AIParsingOrchestrator as AI Parsing Orchestrator (Core Logic)
    participant AIRuleInferenceEngine as AI Rule Inference Engine (Core Logic)
    participant AIServiceAPI as AI Service API (External)
    participant RuleBasedSplitter as Rule-based Splitter (Core Logic)
    participant RuleBasedMapper as Rule-based Mapper (Core Logic)
    participant LabelMilestoneNormalizer as Label/Milestone Normalizer (Core Logic)
    participant DefaultsLoader as Defaults Loader (Infra)
    participant ConfigLoader as Config Loader (Infra)

    User->>StaticFrontend: 1. Issue情報ファイルを選択し、「アップロード＆プレビュー」実行
    activate StaticFrontend
    StaticFrontend->>StaticFrontend: 2. ファイルデータ準備
    StaticFrontend->>BackendAPI: 3. POST /api/v1/parse-file (ファイルデータ)
    activate BackendAPI

    BackendAPI->>AIParsingOrchestrator: 4. Issue解析要求 (ファイル内容全体)
    activate AIParsingOrchestrator
    AIParsingOrchestrator->>ConfigLoader: 5. プロンプトテンプレートパス等取得
    activate ConfigLoader
    ConfigLoader-->>AIParsingOrchestrator: 6. 設定情報 (プロンプトパス等)
    deactivate ConfigLoader

    AIParsingOrchestrator->>AIRuleInferenceEngine: 7. 区切りルール(先頭キー)とキーマッピングルール推論実行
    activate AIRuleInferenceEngine
    AIRuleInferenceEngine->>AIServiceAPI: 8. AIにルール推論を問い合わせ
    activate AIServiceAPI
    AIServiceAPI-->>AIRuleInferenceEngine: 9. 推論されたルール, 信頼度
    deactivate AIServiceAPI
    AIRuleInferenceEngine-->>AIParsingOrchestrator: 10. 推論ルールと信頼度返却
    deactivate AIRuleInferenceEngine

    alt ルール推論失敗 or 先頭キー特定不可 or 信頼度低
        AIParsingOrchestrator->>ConfigLoader: 10a. フォールバック区切りルール指定取得
        activate ConfigLoader
        ConfigLoader-->>AIParsingOrchestrator: 10b. フォールバック区切りルール (あれば)
        deactivate ConfigLoader
        alt フォールバック区切りルールもなし or 適用不可
             AIParsingOrchestrator-->>BackendAPI: 10c. 解析エラー/警告情報生成
        else フォールバック区切りルール適用
             AIParsingOrchestrator->>AIParsingOrchestrator: 10d. フォールバック区切りルールを「決定された区切りルール」とする
        end
    else ルール推論成功 (先頭キー特定)
        AIParsingOrchestrator->>AIParsingOrchestrator: 10e. AI推論の区切りルールを「決定された区切りルール」とする
    end

    AIParsingOrchestrator->>RuleBasedSplitter: 11. 「決定された区切りルール」とファイル内容でIssueブロック分割
    activate RuleBasedSplitter
    RuleBasedSplitter-->>AIParsingOrchestrator: 12. 分割されたIssueブロックリスト
    deactivate RuleBasedSplitter

    AIParsingOrchestrator->>RuleBasedMapper: 13. 推論「キーマッピングルール」とIssueブロックリストでIssueDataへ粗マッピング
    activate RuleBasedMapper
    RuleBasedMapper-->>AIParsingOrchestrator: 14. 粗マッピング済みIssueDataリスト
    deactivate RuleBasedMapper

    AIParsingOrchestrator->>DefaultsLoader: 15. デフォルトのラベル・マイルストーン定義取得
    activate DefaultsLoader
    DefaultsLoader-->>AIParsingOrchestrator: 16. 定義済みラベル・マイルストーンリスト
    deactivate DefaultsLoader

    AIParsingOrchestrator->>LabelMilestoneNormalizer: 17. 粗マッピング済みIssueDataと定義済みリストでラベル・マイルストーン正規化
    activate LabelMilestoneNormalizer
    LabelMilestoneNormalizer-->>AIParsingOrchestrator: 18. 正規化済みIssueDataリスト
    deactivate LabelMilestoneNormalizer

    AIParsingOrchestrator->>AIParsingOrchestrator: 19. ParsedSourceFileContent 生成
    AIParsingOrchestrator-->>BackendAPI: 20. 解析成功 (`ParsedSourceFileContent` or エラー/警告情報)
    deactivate AIParsingOrchestrator

    BackendAPI-->>StaticFrontend: 21. HTTPレスポンス (JSON with ParsedSourceFileContent or エラーJSON)
    deactivate BackendAPI

    StaticFrontend->>StaticFrontend: 22. レスポンスJSONを解釈
    alt 解析成功
        StaticFrontend->>StaticFrontend: 23. Issue一覧をUIに描画 (警告もあれば表示)
        StaticFrontend-->>User: 24. Issue一覧表示 (警告も表示)
    else 解析失敗/エラー
        StaticFrontend->>StaticFrontend: 23a. エラーメッセージをUIに表示
        StaticFrontend-->>User: 24a. エラーメッセージ表示
    end
    deactivate StaticFrontend
```

**シーケンス図の修正ポイント:**
* 参加者を「User」「静的フロントエンド (JS)」「バックエンドAPI (Django/DRF)」とし、その後のコアロジックコンポーネントはバックエンドAPI内部で呼び出される形としました。
* ユーザーの最初のインタラクションは静的フロントエンドに対して行われます。
* 静的フロントエンドとバックエンドAPI間の通信は、HTTPリクエスト（例: `POST /api/v1/parse-file`）とHTTPレスポンス（JSONデータ）で表現しました。
* バックエンドAPIがコアロジックの `AIParsingOrchestrator` を呼び出し、解析結果やエラー情報を受け取ります。
* 静的フロントエンドがAPIからのレスポンスを処理し、UIを更新してユーザーに結果を表示する流れを明確にしました。
* メッセージの番号を振り直しました。
