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

# テスト要件: ラベル・マイルストーン正規化 (TASK-CORELOGIC-LABEL-MILESTONE-NORMALIZER)
- id: TR-Normalization-001
  description: IssueDataのラベルは、github_setup_defaults.ymlに基づき正規化されること。
- id: TR-Normalization-002
  description: IssueDataのマイルストーンは、github_setup_defaults.ymlに基づき正規化されること。
- id: TR-Normalization-003
  description: 正規化に失敗したラベルやマイルストーンは警告ログが出力されること。

# 備考
- API要件、クライアントサイド検証要件、API連携要件はそれぞれ独立しており、重複・矛盾はありません。
- フロントエンドのテスト要件は、API要件とは別に、ユーザー体験向上のためのクライアントサイドでの即時フィードバックと、バックエンドとの通信を検証するものです。
- 【説明責任】US-001のDoD・受け入れ基準を反映し、既存要件と重複するものは統合・拡張し、矛盾はありませんでした。

