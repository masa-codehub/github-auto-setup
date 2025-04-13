import typer
from pathlib import Path
from typing import Optional
# Python 3.9+ なら typing.Annotated, それ未満なら typing_extensions.Annotated
from typing_extensions import Annotated
import importlib.metadata
import sys
import logging

# --- Project Imports ---
from github_automation_tool import __version__
# Infrastructure / Adapters
from github_automation_tool.infrastructure.config import load_settings, Settings
from github_automation_tool.infrastructure.file_reader import read_markdown_file # 関数をインポート
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.adapters.cli_reporter import CliReporter
# Use Cases
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase # ★ 統合UseCase
# Exceptions
from github_automation_tool.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubAuthenticationError, GitHubValidationError
)

# --- Logger Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("github_automation_tool.main") # モジュール名を指定


# --- Typer App ---
app = typer.Typer(
    help="GitHub Automation Tool: Create repositories and issues from a file."
)

# --- Callbacks ---
def version_callback(value: bool):
    if value:
        print(f"GitHub Automation Tool Version: {__version__}")
        raise typer.Exit()

# --- Main Command ---
@app.command()
def run(
    # --- Required Options ---
    file_path: Annotated[Path, typer.Option("--file", help="Path to the input Markdown file.", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, show_default=False)],
    repo_name_input: Annotated[str, typer.Option("--repo", help="Name of the GitHub repository (e.g., 'owner/repo-name' or just 'repo-name').", show_default=False)],
    project_name: Annotated[str, typer.Option("--project", help="Name of the GitHub project (V2) to create or add issues to.", show_default=False)],

    # --- Optional Arguments ---
    config_path: Annotated[Optional[Path], typer.Option("--config", help="Path to a custom configuration file (Currently not used).", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True)] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulate the process without making actual changes on GitHub.")] = False,

    # --- Version Option ---
    version: Annotated[Optional[bool], typer.Option("--version", help="Show the application version and exit.", callback=version_callback, is_eager=True)] = None,
):
    """
    Reads a Markdown file, parses it using AI, and automatically creates
    GitHub repository, project, issues, labels, and milestones (basic MVP flow).
    """
    # 結果表示用の Reporter を最初にインスタンス化
    reporter = CliReporter()

    try:
        # --- 1. 設定読み込み ---
        settings = load_settings()
        log_level_name = settings.log_level.upper()
        numeric_level = getattr(logging, log_level_name, logging.INFO)
        logging.getLogger().setLevel(numeric_level) # Root logger のレベルを設定
        logger.info("Settings loaded successfully.")
        logger.debug(f"Log Level set to: {log_level_name}")
        # APIキーなどの機密情報はデバッグログでも直接表示しない方が安全
        logger.debug(f"GitHub PAT: {'Loaded' if settings.github_pat else 'Not Set'}")
        logger.debug(f"Using AI model: {settings.ai_model}")

        # --- 2. 依存コンポーネントのインスタンス化 (手動DI) ---
        logger.debug("Initializing core components...")
        # file_reader は関数なのでそのまま利用
        github_client = GitHubAppClient(auth_token=settings.github_pat)
        ai_parser = AIParser(settings=settings)
        create_repo_uc = CreateRepositoryUseCase(github_client=github_client)
        create_issues_uc = CreateIssuesUseCase(github_client=github_client)

        # メインとなる統合UseCaseをインスタンス化
        main_use_case = CreateGitHubResourcesUseCase(
            settings=settings,
            file_reader=read_markdown_file, # 関数を渡す
            ai_parser=ai_parser,
            github_client=github_client, # owner取得用に渡す
            create_repo_uc=create_repo_uc,
            create_issues_uc=create_issues_uc,
            reporter=reporter # 結果表示用に渡す
        )
        logger.debug("Core components initialized.")

        # --- 3. メインUseCaseの実行 ---
        logger.info("Executing the main resource creation workflow...")
        # 実行前にINFOログに引数情報を出力
        logger.info(f"Input File Path : {file_path}")
        logger.info(f"Repository Input: {repo_name_input}")
        logger.info(f"Project Name    : {project_name}")
        if config_path:
            logger.info(f"Config File Path: {config_path} (Note: Currently not used)")
        logger.info(f"Dry Run Mode    : {dry_run}")
        logger.info("------------------------------------")

        main_use_case.execute(
            file_path=file_path,
            repo_name_input=repo_name_input,
            project_name=project_name, # 現在はUseCase内で未使用だが渡しておく
            dry_run=dry_run
        )
        logger.info("Workflow execution completed.") # 正常終了ログ

    # --- 4. エラーハンドリング (UseCaseから送出された例外を捕捉) ---
    except FileNotFoundError as e:
        error_message = f"Input file not found: {e}"
        logger.error(error_message)
        print(f"\nERROR: {error_message}", file=sys.stderr) # ユーザーへのフィードバック
        raise typer.Exit(code=1)
    except PermissionError as e:
        error_message = f"Permission denied for input file: {e}"
        logger.error(error_message)
        print(f"\nERROR: {error_message}", file=sys.stderr)
        raise typer.Exit(code=1)
    except IOError as e: # UnicodeDecodeErrorなども含む
        error_message = f"Error reading input file: {e}"
        logger.error(error_message)
        reporter.display_general_error(e, context="reading input file") # 詳細表示
        print(f"\nERROR: {error_message}", file=sys.stderr) # 簡潔なメッセージも出す
        raise typer.Exit(code=1)
    except (ValueError, AiParserError, GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
        # アプリケーション内の予期されたエラー
        error_message = f"Workflow failed: {type(e).__name__} - {e}"
        logger.error(error_message)
        print(f"\nERROR: {error_message}", file=sys.stderr)
        raise typer.Exit(code=1)
    except Exception as e:
        # 予期しないその他の重大なエラー
        error_message = f"An unexpected critical error occurred: {e}"
        logger.exception(error_message) # トレースバック付きでログ記録
        reporter.display_general_error(e, context="during main execution") # 詳細表示
        print(f"\nCRITICAL ERROR: An unexpected error occurred. Check logs for details.", file=sys.stderr)
        raise typer.Exit(code=1)

# スクリプトとして直接実行する場合のエントリーポイント (通常は不要)
# if __name__ == "__main__":
#     app()