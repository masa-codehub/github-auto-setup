import typer
from pathlib import Path
from typing import Optional
# Python 3.9+ なら typing.Annotated, それ未満なら typing_extensions.Annotated を使う
from typing_extensions import Annotated
import importlib.metadata
import sys
import logging  # ロギングのためにインポート
# import os # テストモード削除により不要になった

from github_automation_tool import __version__
# config モジュールから load_settings 関数と Settings 型をインポート
from github_automation_tool.infrastructure.config import load_settings, Settings

# ロガーの基本設定 (アプリケーションの早い段階で設定)
# ログレベルは後で settings から読み込んだ値で上書きします
logging.basicConfig(
    level=logging.INFO,  # デフォルトレベル
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# このモジュール用のロガーを取得
logger = logging.getLogger(__name__)


app = typer.Typer(
    help="GitHub Automation Tool: Create repositories and issues from a file."
)

# バージョン表示用のコールバック関数


def version_callback(value: bool):
    if value:
        print(f"GitHub Automation Tool Version: {__version__}")
        raise typer.Exit()


@app.command()
def run(
    # --- Required Options ---
    file_path: Annotated[Path, typer.Option("--file",
                                            help="Path to the input Markdown file.",
                                            exists=True,
                                            file_okay=True,
                                            dir_okay=False,
                                            readable=True,
                                            resolve_path=True,
                                            show_default=False)],
    repo_name: Annotated[str, typer.Option("--repo",
                                           help="Name of the GitHub repository to create (e.g., 'owner/repo-name' or just 'repo-name').",
                                           show_default=False)],
    project_name: Annotated[str, typer.Option("--project",
                                              help="Name of the GitHub project (V2) to create or add issues to.",
                                              show_default=False)],

    # --- Optional Arguments ---
    config_path: Annotated[Optional[Path], typer.Option("--config",
                                                        help="Path to a custom configuration file.",
                                                        exists=True,
                                                        file_okay=True,
                                                        dir_okay=False,
                                                        readable=True,
                                                        resolve_path=True)] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run",
                                          help="Simulate the process without making actual changes on GitHub.")] = False,

    # --- Version Option ---
    version: Annotated[Optional[bool], typer.Option("--version",
                                                    help="Show the application version and exit.",
                                                    callback=version_callback,
                                                    is_eager=True)] = None,

    # --- ★ テスト用オプションは削除 ---
    # test_mode: Annotated[bool, typer.Option(...)] = False,
):
    """
    Reads a Markdown file, parses it using AI, and automatically creates
    GitHub repository, project, issues, labels, and milestones.
    """
    settings: Settings  # 設定を格納する変数

    # --- 設定ファイルの読み込みとエラーハンドリング ---
    try:
        # ★ test_mode の if ブロックを削除
        settings = load_settings()  # アプリケーション開始時に設定をロード

        # 設定に基づいてログレベルを更新
        log_level_name = settings.log_level.upper()
        numeric_level = getattr(logging, log_level_name, logging.INFO)
        logging.getLogger().setLevel(numeric_level)  # ルートロガーのレベルを設定
        logger.info(f"Log level set to {log_level_name}")

        logger.info("Settings loaded successfully.")
        # デバッグログで設定内容の一部を表示 (APIキーはマスク推奨)
        logger.debug(
            f"GitHub PAT: {'Loaded' if settings.github_pat else 'Not Set'}")
        logger.debug(
            f"OpenAI Key: {'Loaded' if settings.openai_api_key else 'Not Set'}")
        logger.debug(
            f"Gemini Key: {'Loaded' if settings.gemini_api_key else 'Not Set'}")
        logger.debug(f"Using AI model: {settings.ai_model}")

    except ValueError as e:
        # load_settings でエラーが発生した場合
        # エラー詳細は load_settings 内でログ出力されているはず
        logger.critical(f"Configuration error: {e}")  # Criticalレベルでログ出力
        # print(f"\nCritical Error: {e}", file=sys.stderr) # 標準エラーへのprintは必須ではない
        raise typer.Exit(code=1)  # 終了コード 1 でプログラムを終了
    # --- 設定読み込みここまで ---

    # --- logger.info による情報表示 ---
    logger.info("Starting GitHub Automation Tool Core Process...")
    logger.info(f"Input File Path : {file_path}")
    logger.info(f"Repository Name : {repo_name}")
    logger.info(f"Project Name    : {project_name}")  # アラインメント調整
    if config_path:
        # TODO: config_path を実際に利用する処理
        logger.info(
            f"Config File Path: {config_path} (Note: Currently not used)")
    logger.info(f"Dry Run Mode    : {dry_run}")  # アラインメント調整
    logger.info("------------------------------------")
    # ★ info_messages リストと print を使った表示ロジックは削除

    # --- ここに後続の処理を実装していく ---
    # 'settings' オブジェクトを渡して処理を進めます
    logger.info("Placeholder for core application logic...")
    # 例:
    # try:
    #     from github_automation_tool.infrastructure.file_reader import read_markdown_file
    #     from github_automation_tool.use_cases.create_resources import CreateResourcesUseCase
    #     # ... (依存関係の準備)
    #     use_case = CreateResourcesUseCase(...)
    #     use_case.execute(file_path, repo_name, project_name, settings, dry_run)
    #     logger.info("Automation process completed successfully.")
    # except Exception as e:
    #     logger.error(f"An unexpected error occurred: {e}", exc_info=True) # トレースバックも記録
    #     raise typer.Exit(code=1)

    # ★ 最後の print も logger に統一
    finish_message = "--- GitHub Automation Tool Finish (Placeholder) ---"
    logger.info(finish_message)


# スクリプトとして直接実行する場合のエントリーポイント (通常は不要)
# if __name__ == "__main__":
#     app()
