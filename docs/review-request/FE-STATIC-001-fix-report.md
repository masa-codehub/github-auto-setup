## 修正完了報告: FE-STATIC-001 コードレビュー指摘対応

Issue `https://github.com/masa-codehub/github-auto-setup/issues/FE-STATIC-001` のコードレビュー指摘に基づく修正が全て完了しました。

### 主な修正内容

- **CSRFトークン送信ロジックの有効化**: すべてのAPI POSTリクエストでCSRFトークンを適切に送信するよう、`issue_selection.js`および`file_upload.js`を修正。
- **GitHub登録・ローカル保存ボタンのAPI連携**: `top_page.html`の該当ボタンにイベントリスナーを追加し、API経由でサーバー処理を実装。バックエンドにエンドポイント（`/api/v1/github-create-issues/`, `/api/v1/local-save-issues/`）を追加。
- **AI設定フォームの保存・取得API連携**: `issue_selection.js`および`top_page.html`にて、AI設定フォームの保存・取得をAPI経由で行うロジックを新規実装。バックエンドに`/api/v1/ai-settings/`エンドポイントと`UserAiSettings`モデルを追加し、ユーザーごとのAI設定の永続化・取得に対応。
- **FormDataキー名の統一**: すべてのJSで`issue_file`に統一し、API仕様と完全一致。
- **JSファイルのCDN読み込みにintegrity/crossorigin属性追加**: `top_page.html`にて適用。
- **APIエンドポイントのURL統一**: `/api/v1/parse-file`等に統一し、不要な重複エンドポイントを整理。
- **display_logic.test.jsの削除とテスト構成整理**: ESM構成へ統一し、不要なテストファイルを削除。
- **Pydanticバリデーションテスト修正**: テスト内容を現仕様に合わせて整理。
- **コーディングルールの明文化**: `coding-rules.yml`にCR-030, CR-031を追加。

### テスト・検証
- すべての修正に対しテストを追加・修正し、CIパスを確認済みです。
- `test_requirements.md`の要件（TR-FE-STATIC-001～006）をすべて満たしています。

### 備考
- 修正過程・自己修正ループは`coding-rules.yml`に記録・反映済みです。
- 追加のご要望や再レビュー指摘があればご連絡ください。

---
TASK_FIX_COMPLETED
