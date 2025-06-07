## 実装完了報告: TASK-BE-API-US001-FILE-PROCESS-ENDPOINT [BE][Task] US-001: Issueファイル処理APIエンドポイント実装

Issue https://github.com/masa-codehub/github-auto-setup/issues/181 の実装が完了しました。ご確認をお願いします。

### 主な変更点

今回のタスクで作成・変更した主要なファイルは以下の通りです。

- `webapp/app/urls.py`: 新規APIエンドポイントのURLパターンを追加。
- `webapp/app/views.py`: `FileUploadAPIView`を新規作成し、ファイルアップロード、解析呼び出し、キャッシュ保存、レスポンス返却ロジックを実装。
- `webapp/app/tests.py`: `FileUploadAPIView`に対する単体テスト（正常系・異常系）を追記。

### テストと検証

- `test_requirements.md` に以下のテスト要件を追記・更新しました。
  - `TR-API-Upload-001`: 有効なファイル（md, yml, json）をアップロードすると、解析結果のJSONとHTTP 200が返される。
  - `TR-API-Upload-002`: サポート外の拡張子を持つファイルをアップロードすると、HTTP 400エラーが返される。
  - `TR-API-Upload-003`: 10MBを超えるファイルをアップロードすると、HTTP 400エラーが返される。
  - `TR-API-Upload-004`: ファイルを添付せずにリクエストを送信すると、HTTP 400エラーが返される。
  - `TR-API-Upload-005`: コアロジックのAIParserが解析エラー（AiParserError）を発生させた場合、HTTP 400エラーが返される。
  - `TR-API-Upload-006`: 処理中に予期せぬサーバーエラーが発生した場合、HTTP 500エラーが返される。
- 上記要件を網羅するテストケースを実装し、全てのテストがパスすることを確認済みです。

### 設計上の判断と学習事項

実装にあたり、以下の点を考慮・判断しました。

- **【設計判断】**
  - ファイルバリデーションには、既存の`webapp/app/forms.py`内の`FileUploadForm`は直接利用せず、DRFのパーサーと`APIView`内のロジックで実装しました。これは、APIエンドポイントの責務をView内に集約するためです。
  - 解析結果の一時保存には、既存の`webapp/app/models.py`の`ParsedDataCache`モデルを活用し、UIとの状態管理を容易にしました。
  - `views.py`内に`_parse_uploaded_file_content`というプライベートヘルパー関数を定義し、ファイル形式に応じたパーサーの呼び分けと`AIParser`の呼び出しロジックをカプセル化しました。
- **【新規コーディングルールの追加】**
  - **今回の実装プロセスで得られた知見から、再発防止のため `coding-rules.yml` に以下のルールを追加しました。**
  - CR-018: Django REST APIのファイルアップロード時は例外ハンドリングとバリデーションを徹底する

### レビュー依頼

特に以下の点について、重点的にレビューいただけますと幸いです。

- `FileUploadAPIView`における例外処理（`AiParserError`や`Exception`の捕捉）が網羅的かつ適切であるか。
- `core_logic`の`AIParser`の呼び出し方法と、返却された`ParsedRequirementData`のハンドリングに問題がないか。

ご確認のほど、よろしくお願いいたします。

---
TASK_COMPLETED
