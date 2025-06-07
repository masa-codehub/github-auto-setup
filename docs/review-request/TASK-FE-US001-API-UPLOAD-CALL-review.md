# TASK-FE-US001-API-UPLOAD-CALL 実装完了報告

## 概要
静的Web UIからIssueファイルをFormDataでバックエンドAPI（`/api/v1/parse-file`）へ非同期アップロードするフロントエンド機能を実装しました。API呼び出し中のスピナー表示、エラー時のUI通知、TDDによるAPIクライアント関数の単体テストも含みます。

## 実装内容
- `frontend/assets/js/issue_selection.js`
  - `#upload-form`のsubmitイベントリスナー追加（デフォルト動作抑止）
  - `uploadIssueFile(formData)`関数でfetch+FormDataによるAPI呼び出し
  - スピナー表示・ボタン無効化/有効化のUIフィードバック
  - エラー時はBootstrapアラートでUI通知
  - テスト用に`uploadIssueFile`をexport
- `frontend/top_page.html`
  - スピナー要素（`#upload-spinner`）を追加
- `frontend/tests/apiClient.test.js`
  - Jestによる`uploadIssueFile`の単体テスト（成功・失敗ケース、fetchモック）

## テスト・検証
- Node.jsを18系にアップグレードし、Jestテストを実行
- `/app/frontend/tests/apiClient.test.js` の全テストがパス
- UI動作（スピナー、エラー通知）も手動で確認済み

## Definition of Done 達成状況
- [x] フォーム送信イベントリスナー実装
- [x] fetch+FormDataによるAPIクライアント関数実装
- [x] スピナー等のUIフィードバック
- [x] 成功時レスポンス出力、失敗時UI通知
- [x] APIクライアント関数の単体テスト（成功・失敗、モック）
- [x] テスト全件パス

## 備考
- fetch API標準利用、外部ライブラリ追加なし
- Jestテスト実行にはNode.js 18以上が必要

ご確認・レビューをお願いします。
