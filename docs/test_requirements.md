# テスト要件: Issueファイル処理APIエンドポイント (TASK-BE-API-US001-FILE-PROCESS-ENDPOINT)

- id: TR-API-Upload-001
  description: 有効なファイル（md, yml, json）をアップロードすると、解析結果のJSONとHTTP 200が返されること。
- id: TR-API-Upload-002
  description: サポート外の拡張子を持つファイルをアップロードすると、HTTP 400エラーが返されること。
- id: TR-API-Upload-003
  description: 10MBを超えるファイルをアップロードすると、HTTP 400エラーが返されること。
- id: TR-API-Upload-004
  description: ファイルを添付せずにリクエストを送信すると、HTTP 400エラーが返されること。
- id: TR-API-Upload-005
  description: コアロジックのAIParserが解析エラー（AiParserError）を発生させた場合、HTTP 400エラーが返されること。
- id: TR-API-Upload-006
  description: 処理中に予期せぬサーバーエラーが発生した場合、HTTP 500エラーが返されること。

# テスト要件: AIパーサー（区切り・キーマッピングルール推論）
- id: TR-AI-Parse-001
  description: AIパーサーが入力テキストからIssue区切りルール（先頭キー）を正しく推論できること。
- id: TR-AI-Parse-002
  description: AIパーサーが入力テキストからキーマッピングルールを正しく推論できること。
- id: TR-AI-Parse-003
  description: AIパーサーが推論結果の信頼度を評価し、信頼度が低い場合に警告情報を出力できること。
- id: TR-AI-Error-001
  description: AI APIの呼び出しが失敗した場合（認証エラー、APIエラー等）に、AIParserが適切に例外をハンドリングできること。

# テスト要件: フロントエンド (クライアントサイド検証)
- id: TR-FE-Validation-001
  description: 有効なファイル（.md, .yml, .yaml, .json）が選択できること（input要素のaccept属性で制限）。
- id: TR-FE-Validation-002
  description: 許容サイズ（10MB）以下のファイルのみ選択できること（クライアントサイドでバリデーション）。
- id: TR-FE-Validation-003
  description: サポート外の拡張子（.txt等）を選択した場合、エラーメッセージが表示されること（クライアントサイド）。
- id: TR-FE-Validation-004
  description: 10MBを超えるファイルを選択した場合、エラーメッセージが表示されること（クライアントサイド）。

# テスト要件: フロントエンド (API連携)
- id: TR-FE-APICall-001
  description: ファイルアップロード時、バックエンドAPI（/api/v1/parse-file）へのPOSTリクエストがFormData形式で正しく送信されること。
- id: TR-FE-APICall-002
  description: API呼び出しが成功した際、レスポンス（解析結果JSON等）を適切にハンドリングできること。
- id: TR-FE-APICall-003
  description: API呼び出しが失敗した際（ネットワークエラー・サーバーエラー・AI解析エラー）、ユーザーにエラーメッセージが通知されること。

# テスト要件: フロントエンド (Issue一覧表示・アコーディオン・件数インジケータ)
- id: TR-FE-Display-001
  description: APIからのJSONデータに基づき、Issueテーブルが正しく動的に描画されること。
- id: TR-FE-Display-002
  description: Issue件数インジケーターが正しく更新されること。
- id: TR-FE-Interaction-001
  description: Issueタイトルのクリックにより、アコーディオン形式で詳細情報が展開・縮小されること。

# テスト要件: Issue分割ロジック (TASK-CORELOGIC-RULE-BASED-SPLITTER)
- id: TR-Splitter-MD-001
  description: Markdownファイルが水平線（---）ルールで正しくIssueブロックに分割されること。
- id: TR-Splitter-MD-002
  description: Markdownファイルが先頭キー（Title:等）ルールで正しくIssueブロックに分割されること。
- id: TR-Splitter-MD-003
  description: Markdownファイルがヘッダーレベル（##等）ルールで正しくIssueブロックに分割されること。
- id: TR-Splitter-YAML-001
  description: YAMLファイルがリスト形式ルールで正しくIssueブロック（辞書リスト）に分割されること。
- id: TR-Splitter-JSON-001
  description: JSONファイルがリスト形式ルールで正しくIssueブロック（辞書リスト）に分割されること。
- id: TR-Splitter-Edge-001
  description: 空のファイルや区切り文字がないファイルが正しく処理され、空リストが返されること。

# テスト要件: ルールベースIssueマッピング (TASK-CORELOGIC-RULE-BASED-MAPPER)
- id: TR-Map-001
  description: 指定されたキーマッピングルールに基づき、IssueブロックからIssueDataの各フィールド（title, description等）へのマッピングが正しく行われること。
- id: TR-Map-002
  description: 値変換ルール（to_list_by_comma, to_list_by_newline, extract_mentions）が正しく適用されること。
- id: TR-Map-Error-001
  description: titleフィールドがマッピングできない場合にValueErrorを送出すること。
- id: TR-Map-Error-002
  description: マッピングに失敗したフィールドがある場合に警告ログが出力されること。

# テスト要件: ラベル・マイルストーン正規化 (TASK-CORELOGIC-LABEL-MILESTONE-NORMALIZER)
- id: TR-Normalization-001
  description: IssueDataのラベルは、github_setup_defaults.ymlに基づき正規化されること。
- id: TR-Normalization-002
  description: IssueDataのマイルストーンは、github_setup_defaults.ymlに基づき正規化されること。
- id: TR-Normalization-003
  description: 正規化に失敗したラベルやマイルストーンは警告ログが出力されること。

# テスト要件: DRF導入・API認証基盤 (BE-API-DRF-SETUP)
- id: TR-BE-API-DRF-001
  description: requirements.txtにdjangorestframeworkとdjango-cors-headersが追加され、pipでインストールされていることを確認する。
- id: TR-BE-API-DRF-002
  description: /api/healthcheck/エンドポイントがJSONレスポンスを返し、200 OKとなることを確認するテストが存在し、パスすること。
- id: TR-BE-API-DRF-003
  description: カスタムAPIキー認証クラス（BaseAuthentication継承）が正しくAPIキーを検証し、テストで有効・無効なキーの判定ができること。
- id: TR-BE-API-DRF-004
  description: カスタムパーミッションクラス（BasePermission継承）が有効なAPIキーのみアクセスを許可し、テストで不正なリクエストが拒否されること。
- id: TR-BE-API-DRF-005
  description: settings.pyのCORS設定により、指定フロントエンドからのリクエストが許可されることをテストで確認する。
- id: TR-BE-API-DRF-006
  description: urls.pyでAPIルーティングが正しく設定され、healthcheck等のエンドポイントにアクセスできることをテストで確認する。

# テスト要件: フロントエンド静的サイト化・API連携移行 (FE-STATIC-001)
- id: TR-FE-STATIC-001
  description: frontend/base.html, frontend/top_page.html からDjangoテンプレート構文（{% ... %}, {{ ... }}, csrf_token等）が完全に除去されていること。
- id: TR-FE-STATIC-002
  description: Bootstrap 5がCDN経由で読み込まれており、frontend/vendor/bootstrap/ ディレクトリが削除されていること。
- id: TR-FE-STATIC-003
  description: frontend/assets/js/file_upload.js のファイルアップロード処理がfetch APIによる非同期HTTPリクエスト（FormData+POST）に移行されていること。
- id: TR-FE-STATIC-004
  description: frontend/assets/js/display_logic.js のファイル処理結果表示ロジックが、APIから受け取ったJSONデータを元にDOMを動的に操作してレンダリングする実装となっていること。
- id: TR-FE-STATIC-005
  description: frontend/assets/js/issue_selection.js等、全てのUIアクションがDjangoテンプレートに依存せず、API経由でデータ取得・UI操作を行うよう改修されていること。
- id: TR-FE-STATIC-006
  description: GitHub Issue登録・ローカル保存・設定画面の保存/取得等、全てのユーザーアクションがJavaScript経由でDjango APIサーバーのエンドポイントを呼び出す形に統一されていること。
- id: TR-FE-STATIC-007
  description: 設定画面でのAIサービスAPIキーやGitHubリポジトリ名等の保存・取得がAPI経由で正しく行われること。
- id: TR-FE-STATIC-008
  description: 既存および新規のJavaScriptテストコード（frontend/assets/js/tests/, frontend/tests/）が新しいAPIクライアント・DOM操作ロジックに合わせて更新または新規作成され、全てのテストがパスすること。

# テスト要件: GitHubリソース作成・ローカル保存API (BE-API-GITHUB-ACTION)
- id: TR-API-001
  description: /api/create-github-resources/ エンドポイントに有効なIssue情報をPOSTすると、GitHub上にリソース（Issue, リポジトリ, ラベル, マイルストーン）が作成され、正常なJSONレスポンス（CreateGitHubResourcesResultMdl）が返ること。
- id: TR-API-002
  description: /api/create-github-resources/ で認証エラー（無効なGitHub PATやAIサービスAPIキー）が発生した場合、HTTP 401/403エラーと標準化されたエラーレスポンスが返ること。
- id: TR-API-003
  description: /api/save-locally/ エンドポイントに有効なIssue情報をPOSTすると、ローカルファイルに保存され、正常なJSONレスポンスが返ること。
- id: TR-API-004
  description: /api/save-locally/ でファイルシステムエラー（書き込み権限不足等）が発生した場合、HTTP 500エラーと標準化されたエラーレスポンスが返ること。
- id: TR-API-005
  description: いずれのAPIも、リクエストヘッダーやボディからAPIキー（GitHub PAT, AIサービスキー）を安全に抽出し、UseCaseに渡していることをテストで確認する。
- id: TR-API-006
  description: dry_runパラメータをリクエストで受け付け、UseCaseに正しく渡されていることをテストで確認する。
- id: TR-API-007
  description: GitHub APIやファイルシステムのエラー発生時、HTTPステータスコードとエラー詳細を含む標準化JSONで返却されること。
- id: TR-API-008
  description: 上記APIの正常系・異常系を網羅するユニットテストが実装され、全てのテストがパスすること。

# 備考
- API要件、クライアントサイド検証要件、API連携要件はそれぞれ独立しており、重複・矛盾はありません。
- フロントエンドのテスト要件は、API要件とは別に、ユーザー体験向上のためのクライアントサイドでの即時フィードバックと、バックエンドとの通信を検証するものです。
- 【説明責任】US-001のDoD・受け入れ基準を反映し、既存要件と重複するものは統合・拡張し、矛盾はありませんでした。
- 上記の新規要件(DRF導入、静的サイト化)は、一貫性・重複排除・説明責任の原則に基づき、既存要件と重複しないよう新規IDで整理されています。
- 重大な矛盾が発生した場合はCONFLICT_DETECTEDでエスカレーションします。
