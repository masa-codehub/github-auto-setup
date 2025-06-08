# ラベル・マイルストーン正規化処理 設計方針

## 1. 正規化要件
- IssueData内のlabels（リスト）およびmilestone（文字列）を、docs/github_setup_defaults.ymlの定義に基づき正規化する。
- 入力値の大文字・小文字は区別しない（case-insensitive）。
- エイリアス（別名）対応：例えば「バグ」「bug」「不具合」→"type:bug" など、複数表記を1つの正規ラベルに統一。
- 正規化できなかった場合は警告ログを出力し、元の値を保持または除外（要件に応じて選択）。

## 2. 設計方針
- 正規ラベル・マイルストーン定義はgithub_setup_defaults.ymlで管理し、Infrastructure層でロード。
- エイリアス定義はdefaults.yml内で以下のように拡張可能とする：
  ```yaml
  labels:
    - name: "type:bug"
      aliases: ["バグ", "bug", "不具合"]
      ...
  milestones:
    - name: "M2: AIパーサーコア機能実装とAPI詳細化"
      aliases: ["M2", "AIパーサー", "AI milestone"]
      ...
  ```
- 正規化サービス（LabelMilestoneNormalizerSvc）は、
  - 正規定義リスト（ラベル・マイルストーン・エイリアス含む）を引数で受け取る。
  - labelsリスト・milestone文字列を正規化し、IssueDataに再設定する。
  - 未定義値は警告ログを出力。
- 大文字小文字はすべてlower()で比較。
- エイリアスがなければname自身も比較対象に含める。

## 3. 例
- 入力: labels=["バグ", "feature", "TDD"]
- 定義: type:bug (aliases: ["バグ", "bug", "不具合"]), type:feature (aliases: ["feature", "新機能"]), TDD (aliases: ["TDD"])
- 出力: labels=["type:bug", "type:feature", "TDD"]

- 入力: milestone="M2"
- 定義: name: "M2: AIパーサーコア機能実装とAPI詳細化" (aliases: ["M2", "AIパーサー"])
- 出力: milestone="M2: AIパーサーコア機能実装とAPI詳細化"

## 4. ログ出力方針
- 正規化できなかったラベル・マイルストーンは警告レベルでlogger.warningで出力。
- 例: "[LabelMilestoneNormalizer] 未定義ラベル: 'unknown-label'"

---
この設計方針に基づき、次ステップでサービス実装・テストを行う。
