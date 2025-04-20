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
from github_automation_tool.infrastructure.file_reader import read_markdown_file
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.adapters.github_client import GitHubAppClient
from github_automation_tool.adapters.cli_reporter import CliReporter
# Use Cases
from github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase
# Models
from github_automation_tool.domain.models import CreateGitHubResourcesResult, ParsedRequirementData
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
logger = logging.getLogger("github_automation_tool.main")


# --- Typer App ---
app = typer.Typer(
    help="GitHub Automation Tool: Create repositories and issues from a file."
)

# --- Callbacks ---
def version_callback(value: bool):
    if value:
        print(f"GitHub Automation Tool Version: {__version__}")
        raise typer.Exit()

# --- エラーメッセージ出力用のヘルパー関数 ---
def print_error(message: str):
    """
    エラーメッセージをログと標準エラー出力の両方に出力する。
    テストで検証しやすいように標準化する。
    """
    logger.error(message)
    print(f"\nERROR: {message}", file=sys.stderr)

# --- Main Command ---
@app.command()
def run(
    # --- Required Options ---
    file_path: Annotated[Path, typer.Option("--file", help="Path to the input Markdown file.", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, show_default=False)],
    repo_name_input: Annotated[str, typer.Option("--repo", help="Name of the GitHub repository (e.g., 'owner/repo-name' or just 'repo-name').", show_default=False)],
    project_name: Annotated[Optional[str], typer.Option("--project", help="Name of the GitHub project (V2) to create or add issues to.")] = None,

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
        try:
            settings = load_settings()
            log_level_name = settings.log_level.upper()
            numeric_level = getattr(logging, log_level_name, logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            logger.info("Settings loaded successfully.")
            logger.debug(f"Log Level set to: {log_level_name}")
            logger.debug(f"GitHub PAT: {'Loaded' if settings.github_pat else 'Not Set'}")
            logger.debug(f"Using AI model: {settings.ai_model}")
        except ValueError as e:
            # 設定のバリデーションエラーは明示的に補足して標準化されたメッセージを出力
            error_message = f"Configuration error(s) detected: {e}"
            print_error(f"Workflow failed: ValueError - {error_message}")
            raise typer.Exit(code=1)

        # --- 2. 依存コンポーネントのインスタンス化 (手動DI) ---
        logger.debug("Initializing core components...")
        github_client = GitHubAppClient(auth_token=settings.github_pat)
        ai_parser = AIParser(settings=settings)
        create_repo_uc = CreateRepositoryUseCase(github_client=github_client)
        create_issues_uc = CreateIssuesUseCase(github_client=github_client)

        # メインとなる統合UseCaseをインスタンス化（依存性を最小限に）
        main_use_case = CreateGitHubResourcesUseCase(
            github_client=github_client,
            create_repo_uc=create_repo_uc,
            create_issues_uc=create_issues_uc
        )
        logger.debug("Core components initialized.")

        # --- 3. ファイル読み込みとAI解析 (UseCase層から分離) ---
        logger.info("Reading and parsing input file...")
        try:
            # ファイル読み込み
            markdown_content = read_markdown_file(file_path)
            logger.info(f"File read successfully (length: {len(markdown_content)}).")
            
            # AI解析
            logger.info("Parsing content with AI...")
            parsed_data: ParsedRequirementData = ai_parser.parse(markdown_content)
            logger.info(f"AI parsing complete. Found {len(parsed_data.issues)} potential issue(s).")
        except FileNotFoundError as e:
            error_message = f"Input file not found: {e}"
            print_error(error_message)
            raise typer.Exit(code=1)
        except PermissionError as e:
            error_message = f"Permission denied for input file: {e}"
            print_error(error_message)
            raise typer.Exit(code=1)
        except IOError as e:
            error_message = f"Error reading input file: {e}"
            logger.error(error_message)
            reporter.display_general_error(e, context="reading input file")
            print_error(error_message)
            raise typer.Exit(code=1)
        except AiParserError as e:
            error_message = f"AI parsing error: {e}"
            print_error(error_message)
            raise typer.Exit(code=1)

        # --- 4. メインUseCaseの実行 ---
        logger.info("Executing the main resource creation workflow...")
        # 実行前にINFOログに引数情報を出力
        logger.info(f"Input File Path : {file_path}")
        logger.info(f"Repository Input: {repo_name_input}")
        logger.info(f"Project Name    : {project_name if project_name else 'None'}")
        if config_path:
            logger.info(f"Config File Path: {config_path} (Note: Currently not used)")
        logger.info(f"Dry Run Mode    : {dry_run}")
        logger.info("------------------------------------")

        # UseCaseの実行（解析済みデータを渡す）
        result: CreateGitHubResourcesResult = main_use_case.execute(
            parsed_data=parsed_data,
            repo_name_input=repo_name_input,
            project_name=project_name,
            dry_run=dry_run
        )
        
        # 実行結果の表示（責務をReporterに委譲）
        reporter.display_create_github_resources_result(result)
        logger.info("Workflow execution completed.")

    # --- 5. エラーハンドリング (UseCaseから送出された例外を捕捉) ---
    except (GitHubValidationError, GitHubAuthenticationError, GitHubClientError) as e:
        # アプリケーション内の予期されたエラー
        error_message = f"Workflow failed: {type(e).__name__} - {e}"
        print_error(error_message)
        raise typer.Exit(code=1)
    except Exception as e:
        # 予期しないその他の重大なエラー
        error_message = f"An unexpected critical error occurred: {e}"
        logger.exception(error_message)
        reporter.display_general_error(e, context="during main execution")
        print(f"\nCRITICAL ERROR: An unexpected error occurred. Check logs for details.", file=sys.stderr)
        raise typer.Exit(code=1)

# スクリプトとして直接実行する場合のエントリーポイント (通常は不要)
if __name__ == "__main__":
    app()