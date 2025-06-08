## 実装完了報告: TASK-CORELOGIC-RULE-BASED-SPLITTER [Core][Task] US-001: 推論/フォールバックルールに基づくIssueブロック分割処理

Issue `https://github.com/masa-codehub/github-auto-setup/issues/183` の実装が完了しました。ご確認をお願いします。

### 主な変更点

今回のタスクで作成・変更した主要なファイルは以下の通りです。

-   `webapp/core_logic/github_automation_tool/adapters/rule_based_splitter.py` (新規作成)
-   `webapp/core_logic/github_automation_tool/tests/adapters/test_rule_based_splitter.py` (新規作成)
-   `webapp/core_logic/github_automation_tool/adapters/ai_parser.py` (`RuleBasedSplitter`を呼び出すように修正)

### テストと検証

-   `test_requirements.md` に以下のテスト要件を追記・更新しました。
    -   `TR-Splitter-MD-001`: Markdownファイルが水平線ルールで正しく分割される。
    -   `TR-Splitter-MD-002`: Markdownファイルが先頭キールールで正しく分割される。
    -   `TR-Splitter-MD-003`: Markdownファイルがヘッダーレベルルールで正しく分割される。
    -   `TR-Splitter-YAML-001`: YAMLファイルがリスト形式ルールで正しく分割される。
    -   `TR-Splitter-JSON-001`: JSONファイルがリスト形式ルールで正しく分割される。
    -   `TR-Splitter-Edge-001`: 空のファイルや区切り文字がないファイルが正しく処理される。
-   上記要件を網羅するテストケースを実装し、全てのテストがパスすることを確認済みです。
-   上記に加え、策定された**完了定義（DoD）の全ての項目をクリア**していることを確認済みです。

### 設計上の判断と学習事項

実装にあたり、以下の点を考慮・判断しました。

-   **[矛盾解決に関するメモ（もしあれば）]**
    -   該当なし。
-   **[その他の主要な設計判断]**
    -   **責務分離:** Issue分割のロジックは多様なルール（先頭キー、水平線、ヘッダー、リスト形式など）を扱うため、`AIParser`から`RuleBasedSplitterSvc`という独立したサービスクラスに責務を分離しました。これにより、AIによる解釈とルールベースの分割処理が明確に分かれ、それぞれのテスト容易性と保守性が向上しました。
    -   **拡張性:** `RuleBasedSplitterSvc`内部で、ルールの種類に応じた処理メソッドを呼び出す設計としました。これにより、将来的により複雑な区切りルールが追加された場合でも、他のロジックに影響を与えずに拡張が可能です。
-   **【新規コーディングルールの追加】**
    -   **今回の実装プロセスで得られた知見から、再発防止のため `coding-rules.yml` に以下のルールを追加しました。**
    -   `CR-026: 複数の戦略を持つ処理はStrategyパターンで分離する` - 複数の分割ルールを扱うロジックを実装した経験から、同様のケースで再利用可能な設計パターンとしてルール化。

### レビュー依頼

特に以下の点について、重点的にレビューいただけますと幸いです。

-   `RuleBasedSplitterSvc`の責務範囲とインターフェース設計は適切か。
-   Markdown、YAML、JSONに対する各分割ロジックと、それらを検証するテストケースは網羅的か。
-   AI推論ルールとフォールバックルールを組み合わせる際のロジックに考慮漏れはないか。

ご確認のほど、よろしくお願いいたします。

---
TASK_COMPLETED
