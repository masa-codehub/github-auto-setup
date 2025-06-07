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
- id: TR-FE-Upload-001
  description: 有効なファイル（.md, .yml, .yaml, .json）が選択できること（input要素のaccept属性で制限）。
- id: TR-FE-Upload-002
  description: 許容サイズ（10MB）以下のファイルのみ選択できること（クライアントサイドでバリデーション）。
- id: TR-FE-Upload-003
  description: サポート外の拡張子（.txt等）を選択した場合、エラーメッセージが表示されること（クライアントサイド）。
- id: TR-FE-Upload-004
  description: 10MBを超えるファイルを選択した場合、エラーメッセージが表示されること（クライアントサイド）。

# 備考
- 既存要件との重複・矛盾はありませんでした。
- 受け入れ基準の一貫性を優先し、APIエラー時のレスポンス仕様も明記しました。
- 本タスクで追加したTR-FE-Upload-001〜004は、API要件（TR-API-Upload-001〜006）と重複・矛盾しません。UI/UX仕様および受け入れ基準に基づき追加。
- 以上で本タスクのテスト要件定義は完了です。
