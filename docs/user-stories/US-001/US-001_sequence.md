**シーケンス図案: US-001 Web UIでのIssueファイルのアップロード、AIによる区切り・マッピングルール推論と解析、一覧表示**

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant WebUI as Web UI (Django View/Form)
    participant AppService as App Service Layer (Optional)
    participant AIParsingService as AI Parsing Service (Core Logic)
    participant AIRuleInferenceEngine as AI Rule Inference Engine (Core Logic - AIParser内)
    participant RuleBasedSplitter as Rule-based Splitter (Core Logic)
    participant RuleBasedMapper as Rule-based Mapper (Core Logic)
    participant AIServiceAPI as AI Service API (External)

    User->>WebUI: 1. Issue情報ファイルを選択し、「アップロード＆プレビュー」実行
    activate WebUI
    WebUI->>WebUI: 2. ファイル検証 (形式、サイズ)
    alt ファイル検証NG
        WebUI-->>User: 2a. エラーメッセージ表示
    else ファイル検証OK
        WebUI->>AppService: 3. ファイル内容処理要求 (ファイル内容)
        activate AppService
        AppService->>AIParsingService: 4. Issue解析要求 (ファイル内容全体)
        activate AIParsingService
        AIParsingService->>AIRuleInferenceEngine: 5. ルール推論実行 (ファイル内容全体)
        activate AIRuleInferenceEngine
        AIRuleInferenceEngine->>AIServiceAPI: 6. AIにルール推論を問い合わせ
        activate AIServiceAPI
        AIServiceAPI-->>AIRuleInferenceEngine: 7. 推論されたルール (区切りルール, マッピングルール)
        deactivate AIServiceAPI
        AIRuleInferenceEngine-->>AIParsingService: 8. 推論ルール返却
        deactivate AIRuleInferenceEngine

        alt ルール推論失敗
            AIParsingService-->>AppService: 8a. 解析エラー情報返却
        else ルール推論成功
            AIParsingService->>RuleBasedSplitter: 9. 推論された「区切りルール」とファイル内容でIssueブロックに分割
            activate RuleBasedSplitter
            RuleBasedSplitter-->>AIParsingService: 10. 分割されたIssueブロックリスト (`IntermediateParsingResult`)
            deactivate RuleBasedSplitter

            AIParsingService->>RuleBasedMapper: 11. 推論された「マッピングルール」とIssueブロックリストで`IssueData`へマッピング
            activate RuleBasedMapper
            RuleBasedMapper-->>AIParsingService: 12. マッピング済み`IssueData`リストとメタ情報 (`ParsedSourceFileContent`)
            deactivate RuleBasedMapper

            AIParsingService-->>AppService: 13. 解析成功 (`ParsedSourceFileContent`) 返却
        end
        deactivate AIParsingService
        AppService-->>WebUI: 14. 処理結果 (ParsedSourceFileContent or エラー情報)
        deactivate AppService

        alt 解析成功
            WebUI->>WebUI: 15. Issue一覧表示準備 (テンプレートへデータ渡し)
            WebUI-->>User: 16. Issue一覧画面表示
        else 解析失敗
            WebUI->>WebUI: 15a. エラー表示準備
            WebUI-->>User: 16a. エラーメッセージ表示
        end
    end
    deactivate WebUI

```

**シーケンス図の説明:**

1.  **ユーザー**がWeb UI上でファイルを選択し、アップロードアクションを実行します。
2.  **Web UI (Django View/Form)** は受け取ったファイルを検証します（形式、サイズ）。
    * 検証NGの場合、ユーザーにエラーメッセージを表示します。
3.  ファイル検証OKの場合、**Web UI** は（導入されていれば）**App Service Layer** にファイル内容の処理を要求します。
    * *サービス層がない場合は、Web UI が直接 AI Parsing Service を呼び出す形になります。*
4.  **App Service Layer** は、**AI Parsing Service**（コアロジック内の中核サービス）にIssue解析を要求し、ファイル内容全体を渡します。
5.  **AI Parsing Service** は、まず内部の **AI Rule Inference Engine** にファイル内容全体を渡し、区切りルールとフィールドマッピングルールの推論を実行させます。
6.  **AI Rule Inference Engine** は、設定されたAIモデル（OpenAI/Gemini）の**AI Service API** と通信し、ルールを推論します。
7.  **AI Service API** は推論結果（区切りルール、マッピングルール）を返します。
8.  **AI Rule Inference Engine** は推論されたルールを **AI Parsing Service** に返します。
    * ルール推論に失敗した場合、エラー情報が返されます。
9.  **AI Parsing Service** は、AIが推論した「区切りルール」とファイル内容を **Rule-based Splitter** に渡し、Issueブロックのリスト (`IntermediateParsingResult`) を生成させます。
10. **Rule-based Splitter** は分割結果を返します。
11. **AI Parsing Service** は、AIが推論した「フィールドマッピングルール」と、分割されたIssueブロックリストを **Rule-based Mapper** に渡し、各ブロックを `IssueData` オブジェクトに変換させ、最終的に `ParsedSourceFileContent` を生成します。
12. **Rule-based Mapper** は `ParsedSourceFileContent` を返します。
13. **AI Parsing Service** は、処理結果（成功なら `ParsedSourceFileContent`、失敗ならエラー情報）を **App Service Layer** に返します。
14. **App Service Layer** は、その結果を **Web UI (Django View)** に返します。
15. **Web UI** は、結果に応じてIssue一覧表示の準備、またはエラー表示の準備を行います。
16. **Web UI** は、最終的な画面を**ユーザー**に表示します。
