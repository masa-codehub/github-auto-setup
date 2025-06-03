# US-001: Web UIでのIssueファイルのアップロード、AIによる区切り・キーマッピングルール推論と解析、一覧表示 - アクティビティ図

このドキュメントは、ユーザーストーリー US-001 の主要なアクティビティフローを図示します。

```mermaid
graph TD
    subgraph "静的フロントエンド (Webブラウザ)"
        A1["start"] --> A2("ファイル選択UIを表示");
        A2 --> A3("Issue情報ファイルを選択");
        A3 --> A4("「アップロード＆プレビュー」実行<br>(ファイルデータを準備)");
        A4 --> A5("バックエンドAPIへ<br>ファイル解析リクエスト送信");
    end

    subgraph "バックエンドAPI (Django/DRF)"
        B1["APIエンドポイントで<br>ファイル解析リクエスト受信<br>(ファイルデータ含む)"] --> B2{"ファイル検証\n(形式・サイズ)"};
        B2 -- "OK" --> B3("ファイル内容全体を<br>コアロジックへ連携");
        B2 -- "NG (ファイル検証エラー)" --> B4("エラーレスポンス生成 (例: 400 Bad Request)");
        B4 --> B5("API経由でエラー情報返却");

        subgraph "コアロジック (AI Parsing Service)"
            D1["ファイル内容全体受信"] --> D2("AI Rule Inference Engine実行:\n(プロンプトテンプレートとファイル内容に基づき)\n1. Issue区切りルール推論 (主に先頭キー/開始パターン特定)\n2. キーマッピングルール推論");
            D2 --> D3{"ルール推論成功?\n(信頼度判定含む)"};
            D3 -- "成功 (先頭キー特定など)" --> D3a["推論された「区切りルール(先頭キー)」と\n「キーマッピングルール」を保持"];
            D3a --> D4("Rule-based Splitter実行:\n推論された「先頭キー区切りルール」で\nIssueブロック分割");
            D3 -- "失敗 or 先頭キー特定不可" --> D3b("フォールバック区切りルール適用検討\n(config.yamlの指定や共通パターン)");
            D3b --> D3c{"フォールバックで分割可能?"};
            D3c -- "はい" --> D4;
            D3c -- "いいえ" --> D8("解析エラー/警告情報生成 (コアロジック内)");
            D4 --> D5("Rule-based Mapper実行:\n推論「キーマッピングルール」で\n各ブロックをIssueDataの各フィールドへマッピング");
            D5 --> D5a("Label/Milestone Normalizer実行:\n抽出記述をdefaults.ymlと照合・正規化");
            D5a --> D6("ParsedSourceFileContent 生成");
            D6 --> D7{"解析全体成功?"};
            D7 -- "失敗 (マッピング/正規化エラーなど)" --> D8;
        end
        B3 --> D1;

        D7 -- "成功" --> B6("成功レスポンス生成 (ParsedSourceFileContent含むJSON)");
        B6 --> B7("API経由で解析結果返却");
        D8 --> B8("エラー/警告レスポンス生成 (JSON)");
        B8 --> B5;
    end

    subgraph "静的フロントエンド (Webブラウザ)"
        A5 -- API Response --> A6{"APIレスポンス受信"};
        A6 -- "成功 (解析結果JSON)" --> A7("JSONデータを解釈");
        A7 --> A8("Issue一覧と詳細を\n動的にUIに描画<br>(必要なら警告も表示)");
        A8 --> A10["stop"];
        A6 -- "エラー/警告 (エラーJSON)" --> A9("エラー/警告メッセージをUIに表示");
        A9 --> A10;
    end

    classDef user fill:#E6E6FA,stroke:#333,stroke-width:2px; %% Renamed to frontend
    classDef backend_api fill:#FFFACD,stroke:#333,stroke-width:2px;
    classDef core_logic_partition fill:#98FB98,stroke:#333,stroke-width:1px;

    class A1,A2,A3,A4,A5,A6,A7,A8,A9,A10 user; %% Renamed to frontend
    class B1,B2,B3,B4,B5,B6,B7,B8 backend_api;
    class D1,D2,D3,D3a,D3b,D3c,D4,D5,D5a,D6,D7,D8 core_logic_partition;
```

**アクティビティ図の修正ポイント:**
* スイムレーンを「静的フロントエンド (Webブラウザ)」と「バックエンドAPI (Django/DRF)」に明確に分離し、コアロジックはバックエンドAPIの内部処理として位置づけました。
* ユーザーのアクションはフロントエンド内で完結し、フロントエンドがバックエンドAPIと通信する形に変更しました（A4→A5、A5→A6）。
* バックエンドAPIはリクエストを受け付け、コアロジックを実行し、結果（JSON）をレスポンスとして返す流れを明確にしました（B1→B7またはB5）。
* フロントエンドはAPIレスポンスを受け取り、UIを動的に描画するかエラーを表示する流れを明確にしました（A6→A8またはA9）。
* クラス名を `user` から `frontend` に変更（ただしMermaidの予約語ではないので、見た目上の区別のため）。
