## 実装完了報告: TASK-CORELOGIC-RULE-BASED-MAPPER [Core][Task] US-001: 推論ルールに基づくIssueDataへのマッピング処理

Issue `https://github.com/masa-codehub/github-auto-setup/issues/184` の実装が完了しました。ご確認をお願いします。

### 主な変更点

今回のタスクで作成・変更した主要なファイルは以下の通りです。

-   `webapp/core_logic/github_automation_tool/services/rule_based_mapper.py`: (新規作成) 推論されたキーマッピングルールに基づき、Issueブロックを`IssueData`オブジェクトに変換する`RuleBasedMapperService`を実装。
-   `webapp/core_logic/tests/services/test_rule_based_mapper.py`: (新規作成) `RuleBasedMapperService`の単体テスト。正常系、異常系、各種値変換ルールのテストケースを網羅。
-   `docs/plans/TASK-CORELOGIC-RULE-BASED-MAPPER-plan.yml`: (新規作成) 本タスクの実装計画。

### テストと検証

-   `docs/test_requirements.md` に以下のテスト要件を追記・更新しました。
    -   `TR-Map-001`: 指定されたキーマッピングルールに基づき、Issueブロックから`IssueData`の各フィールド（title, description等）へのマッピングが正しく行われる。
    -   `TR-Map-002`: 値変換ルール（`to_list_by_comma`, `to_list_by_newline`, `extract_mentions`）が正しく適用される。
    -   `TR-Map-Error-001`: `title`フィールドがマッピングできない場合に`ValueError`を送出する。
    -   `TR-Map-Error-002`: マッピングに失敗したフィールドがある場合に警告ログが出力される。
-   上記要件を網羅するテストケースを実装し、全てのテストがパスすることを確認済みです。
-   上記に加え、策定された**完了定義（DoD）の全ての項目をクリア**していることを確認済みです。

### 設計上の判断と学習事項

実装にあたり、以下の点を考慮・判断しました。

-   **[その他の主要な設計判断]**
    -   クリーンアーキテクチャの原則に従い、ルールに基づくマッピングという具体的なロジックを`AIParser`から分離し、独立した`RuleBasedMapperService`として`services`レイヤーに実装しました。これにより、AIによるルール推論と、ルール適用による決定論的なマッピングの責務が明確に分離されました。
    -   値の抽出・変換ルールは、将来的な拡張性を考慮し、ルール名と対応する変換関数をマッピングする辞書ベースのディスパッチ構造としました。これにより、新しい変換ルールを容易に追加できます。
-   **【新規コーディングルールの追加】**
    -   **今回の実装プロセスで得られた知見から、再発防止のため `coding-rules.yml` に以下のルールを追加しました。**
        -   `CR-026: データ変換ロジックは独立した純粋関数としてカプセル化する`

### レビュー依頼

特に以下の点について、重点的にレビューいただけますと幸いです。

-   `RuleBasedMapperService`の実装が、単一責任の原則を遵守し、テスト可能な形で設計されているか。
-   値の抽出・変換ルールの実装方法が、将来的な拡張に対して柔軟であるか。
-   テストケースが、多様な入力キーやフォーマットの揺らぎに対して十分な網羅性を確保できているか。

ご確認のほど、よろしくお願いいたします。

---
TASK_COMPLETED
