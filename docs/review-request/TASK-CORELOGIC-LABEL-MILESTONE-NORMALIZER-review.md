# TASK-CORELOGIC-LABEL-MILESTONE-NORMALIZER レビューコメント

## 概要
- IssueDataオブジェクトのラベル・マイルストーンを、`docs/github_setup_defaults.yml`の定義に基づき正規化するサービス（LabelMilestoneNormalizerSvc）を新規実装。
- テスト要件（TR-Normalization-001～003）を追加し、TDDで単体テストを作成・全件パスを確認。
- サービスを`create_github_resources.py`のユースケースに統合し、E2Eテストも全件パス。
- importパス解決の問題により一時的にロジックをインライン化したが、最終的には分離・再利用可能な形に戻す方針。

## 実装・設計のポイント
- 正規化は大文字小文字・エイリアス対応・未定義値の警告出力を含む。
- 設計方針・エイリアス・ケース感度等の詳細は`plans/TASK-CORELOGIC-LABEL-MILESTONE-NORMALIZER-design.md`に明記。
- テスト要件・DoD・受け入れ基準を満たすことを確認。

## テスト
- 単体テスト（test_label_milestone_normalizer.py）で正常系・異常系・警告出力を網羅。
- 統合後、全体テストスイート（pytest webapp/core_logic/github_automation_tool/tests/）でリグレッションなしを確認。

## 新規コーディングルール
- ラベル・マイルストーン等の正規化ロジックは再利用可能な形で`adapters`等に分離し、import設計・依存性に注意すること（CR-CORELOGIC-001）。

## 備考
- importパス問題で一時的にインライン化したが、恒久対応としては分離・再利用性を重視する。
- 詳細はplan/designドキュメント・テスト要件・実装コードを参照。
