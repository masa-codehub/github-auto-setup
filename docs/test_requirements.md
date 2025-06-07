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
- id: TR-FE-API-CALL-001
  description: ファイルアップロード時、バックエンドAPI（/api/v1/parse-file）へのPOSTリクエストがFormData形式で正しく送信されること。
- id: TR-FE-API-CALL-002
  description: API呼び出しが成功した際、レスポンス（解析結果JSON等）を適切にハンドリングできること。
- id: TR-FE-API-CALL-003
  description: API呼び出しが失敗した際（ネットワークエラー・サーバーエラー）、ユーザーにエラーメッセージが通知されること。

# 備考
- 既存要件との重複・矛盾はありませんでした。
- 受け入れ基準の一貫性を優先し、APIエラー時のレスポンス仕様も明記しました。
