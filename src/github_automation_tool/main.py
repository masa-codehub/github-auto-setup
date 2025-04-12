import typer
from pathlib import Path
# Python 3.9+ なら typing.Annotated, それ未満なら typing_extensions.Annotated
from typing import Optional  # Python 3.10+なら | None で書ける
from typing_extensions import Annotated
import importlib.metadata  # バージョン情報取得用

# from github_automation_tool.infrastructure.config import Settings # 設定クラスを使う場合

# アプリケーションのバージョンを pyproject.toml から取得 (例)
try:
    __version__ = importlib.metadata.version("github-automation-tool")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.1.0"  # pyproject.toml がない場合などのフォールバック

app = typer.Typer(
    help="GitHub Automation Tool: Create repositories and issues from a file.")

# バージョン表示用のコールバック関数


def version_callback(value: bool):
    if value:
        print(f"GitHub Automation Tool Version: {__version__}")
        raise typer.Exit()  # バージョン表示後に終了


@app.command()
def run(  # 関数名は main より run などの方が他の予約語と被りにくいかも
    # --- Required Options ---
    file_path: Annotated[Path, typer.Option("--file",
                                            help="Path to the input Markdown file.",
                                            exists=True,       # ファイルが存在するかチェック
                                            file_okay=True,    # ファイルであることを許可
                                            dir_okay=False,    # ディレクトリは不許可
                                            readable=True,     # 読み取り可能かチェック
                                            resolve_path=True,  # 絶対パスに解決
                                            show_default=False)],  # デフォルト値をヘルプに表示しない
    repo_name: Annotated[str, typer.Option("--repo",
                                           help="Name of the GitHub repository to create (e.g., 'owner/repo-name' or just 'repo-name').",
                                           show_default=False)],
    project_name: Annotated[str, typer.Option("--project",
                                              help="Name of the GitHub project (V2) to create or add issues to.",
                                              show_default=False)],

    # --- Optional Arguments ---
    config_path: Annotated[Optional[Path], typer.Option("--config",  # Optional[Path] or Path | None
                                                        help="Path to a custom configuration file.",
                                                        exists=True,
                                                        file_okay=True,
                                                        dir_okay=False,
                                                        readable=True,
                                                        resolve_path=True)] = None,  # デフォルトはNone
    dry_run: Annotated[bool, typer.Option("--dry-run",
                                          help="Simulate the process without making actual changes on GitHub.")] = False,  # デフォルトはFalse

    # --- Version Option ---
    version: Annotated[Optional[bool], typer.Option("--version",  # Optional[bool] or bool | None
                                                    help="Show the application version and exit.",
                                                    callback=version_callback,
                                                    is_eager=True)] = None,  # is_eager=Trueで他の引数より先に評価
):
    """
    Reads a Markdown file, parses it using AI, and automatically creates
    GitHub repository, project, issues, labels, and milestones.
    """
    # まずは受け取った引数を表示して確認
    print("--- GitHub Automation Tool Start ---")
    print(f"Input File Path : {file_path}")
    print(f"Repository Name : {repo_name}")
    print(f"Project Name    : {project_name}")
    if config_path:
        print(f"Config File Path: {config_path}")
    print(f"Dry Run Mode    : {dry_run}")
    print("------------------------------------")

    # --- ここに後続の処理を実装していく ---
    # 例:
    # settings = load_settings(config_path) # 設定読み込み
    # file_content = read_file(file_path) # ファイル読み込み (次のIssue)
    # parsed_data = parse_with_ai(file_content, settings) # AI解析
    # create_github_resources(parsed_data, repo_name, project_name, settings, dry_run) # GitHub操作

    print("--- GitHub Automation Tool Finish (Placeholder) ---")

# スクリプトとして直接実行する場合のエントリーポイント
# 通常は pyproject.toml の [project.scripts] などで設定して呼び出す
# if __name__ == "__main__":
#     app()
