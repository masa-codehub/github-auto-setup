import typer
from pathlib import Path
from typing import Optional
# Python 3.9+ なら typing.Annotated, それ未満なら typing_extensions.Annotated
from typing_extensions import Annotated
import importlib.metadata
try:
    __version__ = importlib.metadata.version("core_logic")
except importlib.metadata.PackageNotFoundError:
    __version__ = "dev"
import sys
import logging

# githubkit から GitHub クラスをインポート
from githubkit import GitHub

# --- Project Imports ---
# Infrastructure / Adapters
from core_logic.infrastructure.config import load_settings, Settings
from core_logic.infrastructure.file_reader import read_markdown_file
from core_logic.adapters.ai_parser import AIParser
from core_logic.adapters.github_rest_client import GitHubRestClient
from core_logic.adapters.cli_reporter import CliReporter
from core_logic.adapters.github_graphql_client import GitHubGraphQLClient
from core_logic.adapters.assignee_validator import AssigneeValidator
from core_logic.use_cases.create_github_resources import CreateGitHubResourcesUseCase
from core_logic.use_cases.create_repository import CreateRepositoryUseCase
from core_logic.use_cases.create_issues import CreateIssuesUseCase
from core_logic.domain.models import CreateGitHubResourcesResult, ParsedRequirementData
from core_logic.domain.exceptions import (
    AiParserError, GitHubClientError, GitHubAuthenticationError, GitHubValidationError
)
from pydantic import ValidationError

# --- Logger Setup ---
# 基本的な設定のみ行い、レベルは load_settings 後に設定
logging.basicConfig(
    level=logging.WARNING,  # 初期レベルは WARNING にしておく
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("core_logic.main")


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
    import sys
    print("DEBUG: print_error called", file=sys.stderr)
    import typer
    typer.echo(message, err=True)

# --- Main Command ---


@app.command()
def run(
    # --- Required Options ---
    file_path: Annotated[Path, typer.Option("--file", help="Path to the input Markdown file.", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True, show_default=False)],
    repo_name_input: Annotated[str, typer.Option("--repo", help="Name of the GitHub repository (e.g., 'owner/repo-name' or just 'repo-name').", show_default=False)],

    # --- Optional Arguments ---
    config_file: Annotated[Optional[Path], typer.Option(
        "--config-file", help="Path to the YAML configuration file.", file_okay=True, dir_okay=False, readable=True, resolve_path=True)] = Path("config.yaml"),
    project_name: Annotated[Optional[str], typer.Option(
        "--project", help="Name of the GitHub project (V2) to add issues to.")] = None,
    dry_run: Annotated[bool, typer.Option(
        "--dry-run", help="Simulate the process without making actual changes on GitHub.")] = False,
    version: Annotated[Optional[bool], typer.Option(
        "--version", help="Show the application version and exit.", callback=version_callback, is_eager=True)] = None,
):
    # --- 設定ロードと初期化 ---
    try:
        settings = load_settings(config_file=config_file)
    except ValidationError as e:
        msg = f"Configuration validation error(s): {e}"
        print_error(msg)
        raise typer.Exit(code=1)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(code=1)
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        raise typer.Exit(code=1)

    reporter = CliReporter()
    # settings: Optional[Settings] = None # 初期化

    try:
        # --- 1. 設定読み込み ---
        logger.info(f"Loading settings using config file: {config_file}")
        # settings = load_settings(config_file=config_file)

        # ログレベルを設定から適用
        log_level_name = settings.final_log_level  # 最終的なログレベルを使用
        numeric_level = getattr(logging, log_level_name, logging.INFO)
        # ルートロガーとメインロガーの両方に設定
        logging.getLogger().setLevel(numeric_level)
        logger.setLevel(numeric_level)
        logger.info(f"Log level set to: {log_level_name}")  # INFOレベルで出力

        # --- 2. 依存コンポーネントのインスタンス化 (手動DI) ---
        logger.debug("Initializing core components...")
        # 2.1 githubkitのベースインスタンス作成
        try:
            github_instance = GitHub(settings.github_pat.get_secret_value())
        except Exception as e:
            logger.error(
                f"Failed to initialize GitHub instance: {e}", exc_info=True)
            raise GitHubAuthenticationError(
                f"Failed to initialize GitHub client: {e}", original_exception=e) from e

        # 個別のクライアントをインスタンス化
        rest_client = GitHubRestClient(github_instance=github_instance)
        graphql_client = GitHubGraphQLClient(github_instance=github_instance)
        assignee_validator = AssigneeValidator(rest_client=rest_client)
        ai_parser = AIParser(settings=settings)

        # --- PAT認証チェックを追加 ---
        try:
            rest_client.get_authenticated_user()
        except Exception as e:
            logger.error(f"GitHub PAT authentication failed: {e}")
            raise GitHubAuthenticationError(
                f"GitHub PAT authentication failed: {e}") from e

        # UseCaseに適切なクライアントを注入
        create_repo_uc = CreateRepositoryUseCase(
            github_client=rest_client)  # 修正: rest_client を渡す
        create_issues_uc = CreateIssuesUseCase(
            rest_client=rest_client,  # 修正: rest_client を渡す
            assignee_validator=assignee_validator  # AssigneeValidator を渡す
        )
        main_use_case = CreateGitHubResourcesUseCase(
            rest_client=rest_client,       # 修正
            graphql_client=graphql_client,  # 追加
            create_repo_uc=create_repo_uc,
            create_issues_uc=create_issues_uc
        )
        logger.debug("Core components initialized.")

        # --- 3. ファイル読み込みとAI解析 (UseCase層から分離) ---
        logger.info("Reading and parsing input file...")
        try:
            markdown_content = read_markdown_file(file_path)
            logger.info(
                f"File read successfully (length: {len(markdown_content)}).")

            logger.info("Parsing content with AI...")
            # まず信頼度推論（ルール推論）
            suggested_rules = ai_parser.infer_rules(markdown_content)
            if suggested_rules.confidence < 0.7:
                warn_msg = ("AIパーサーの信頼度が低いため処理を中断します。\n"
                            f"警告: {'; '.join(suggested_rules.warnings)}\n"
                            "入力ファイルや書式を見直してください。修正後に再度お試しください。")
                print_error(warn_msg)
                raise typer.Exit(code=1)
            parsed_data: ParsedRequirementData = ai_parser.parse(
                markdown_content)
            logger.info(
                f"AI parsing complete. Found {len(parsed_data.issues)} potential issue(s).")
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
            print_error(error_message)
            raise typer.Exit(code=1)
        except AiParserError as e:
            error_message = f"AI parsing error: {e}"
            print_error(error_message)
            raise typer.Exit(code=1)

        # --- 4. メインUseCaseの実行 ---
        logger.info("Executing the main resource creation workflow...")
        logger.info(f"Input File Path : {file_path}")
        logger.info(f"Config File Path: {config_file.resolve()}")
        logger.info(f"Repository Input: {repo_name_input}")
        logger.info(
            f"Project Name    : {project_name if project_name else 'None'}")
        logger.info(f"Dry Run Mode    : {dry_run}")
        logger.info("------------------------------------")
        result: CreateGitHubResourcesResult = main_use_case.execute(
            parsed_data=parsed_data,
            repo_name_input=repo_name_input,
            project_name=project_name,
            dry_run=dry_run
        )

        reporter.display_create_github_resources_result(result)
        logger.info("Workflow execution completed.")

    except ValidationError as e:
        error_message = f"Configuration validation error(s): {e}"
        print_error(error_message)
        raise typer.Exit(code=1)
    except ValueError as e:
        error_message = f"Value error: {e}"
        print_error(error_message)
        raise typer.Exit(code=1)
    except (GitHubAuthenticationError, GitHubClientError) as e:
        error_message = f"Workflow failed: {type(e).__name__} - {e}"
        print_error(error_message)
        raise typer.Exit(code=1)
    except Exception as e:
        error_message = f"An unexpected critical error occurred: {e}"
        print_error(error_message)
        raise typer.Exit(code=1)


# スクリプトとして直接実行する場合のエントリーポイント
if __name__ == "__main__":
    app()
