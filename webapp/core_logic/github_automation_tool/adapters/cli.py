# src/github_automation_tool/adapters/cli.py
"""
CLIアダプター: コマンドラインインターフェースの処理を担当するモジュール
"""

import typer
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from ..domain.models import ParsedRequirementData, CreateGitHubResourcesResult
from ..domain.exceptions import (
    AiParserError, GitHubClientError, GitHubAuthenticationError, GitHubValidationError
)

logger = logging.getLogger(__name__)

class Cli:
    """
    コマンドラインインターフェースのラッパークラス。
    Typer CLIアプリケーションのハンドラーとして機能し、
    ユーザー入力を適切に処理してビジネスロジックに渡します。
    """

    def __init__(self, app: typer.Typer):
        """
        Args:
            app: Typerアプリケーションインスタンス
        """
        self.app = app
        logger.debug("CLI adapter initialized")

    def format_option(self, option_name: str, value: Any) -> str:
        """
        オプション値を文字列形式にフォーマットします。
        
        Args:
            option_name: オプション名
            value: オプション値
            
        Returns:
            str: フォーマットされた文字列
        """
        if value is None:
            return f"{option_name}: Not specified"
        
        if isinstance(value, Path):
            return f"{option_name}: {value.resolve()}"
            
        if isinstance(value, bool):
            return f"{option_name}: {'Enabled' if value else 'Disabled'}"
            
        return f"{option_name}: {value}"
        
    def format_options_summary(self, options: Dict[str, Any]) -> List[str]:
        """
        オプションの概要をフォーマットされた文字列のリストにして返します。
        
        Args:
            options: オプション名と値の辞書
            
        Returns:
            List[str]: フォーマットされたオプションのリスト
        """
        result = []
        for name, value in options.items():
            result.append(self.format_option(name, value))
        return result

    def validate_input(self, file_path: Path, repo_name: str) -> bool:
        """
        入力値の基本的な検証を行います。
        
        Args:
            file_path: 入力ファイルのパス
            repo_name: リポジトリ名
            
        Returns:
            bool: すべての検証をパスした場合はTrue
            
        Raises:
            ValueError: 入力が無効な場合
        """
        if not file_path:
            raise ValueError("Input file path is required")
            
        if not file_path.exists():
            raise ValueError(f"Input file does not exist: {file_path}")
            
        if not repo_name:
            raise ValueError("Repository name is required")
            
        return True