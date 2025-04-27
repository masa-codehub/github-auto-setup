import os
import yaml
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class FileReaderError(Exception):
    """ファイル読み込み操作に関する例外の基底クラス"""
    pass


def file_exists(file_path: Path) -> bool:
    """
    指定されたパスにファイルが存在するかを確認します

    Args:
        file_path: 確認対象のファイルパス

    Returns:
        bool: ファイルが存在する場合はTrue、それ以外はFalse
    """
    return file_path.is_file()


def read_markdown_file(file_path: Path) -> str:
    """
    Reads the content of a Markdown file specified by the path.

    Args:
        file_path: The pathlib.Path object pointing to the Markdown file.
                   Assumes the path has been validated for existence and readability
                   by the CLI layer (Typer) to some extent, but includes basic checks.

    Returns:
        The content of the file as a string.

    Raises:
        FileReaderError: If any error occurs during file reading.
    """
    try:
        if not file_path.is_file():
            if file_path.exists():
                raise FileNotFoundError(
                    f"Path exists but is not a file: {file_path}")
            else:
                raise FileNotFoundError(f"File not found: {file_path}")

        if not os.access(file_path, os.R_OK):
            raise PermissionError(
                f"Permission denied when reading file: {file_path}")

        with file_path.open(mode='r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError as e:
        logger.error(f"File not found: {file_path}")
        raise FileReaderError("File not found") from e
    except UnicodeDecodeError as e:
        logger.error(f"Unicode decode error when reading file '{file_path}': {e}")
        raise FileReaderError(f"Failed to decode file: {e}") from e
    except (IOError, OSError, PermissionError) as e:
        logger.error(f"Failed to read file '{file_path}': {e}")
        raise FileReaderError("Failed to read file") from e


def read_yaml_file(file_path: Path) -> dict:
    """
    YAMLファイルを読み込み、Pythonの辞書として解析します。

    Args:
        file_path: YAMLファイルへのpathlib.Pathオブジェクト

    Returns:
        YAMLコンテンツを表す辞書

    Raises:
        FileReaderError: ファイル読み込みやYAML解析時のエラー
    """
    try:
        if not file_path.is_file():
            raise FileNotFoundError(f"YAML file not found: {file_path}")

        with file_path.open(mode='r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
        
        # コンテンツがNoneまたは辞書型でない場合はエラー
        if content is None or not isinstance(content, dict):
            raise yaml.YAMLError(f"Invalid YAML format: content is {type(content).__name__}, not a dictionary")
            
        return content
    except FileNotFoundError as e:
        logger.error(f"YAML file not found: {file_path}")
        raise FileReaderError("YAML file not found") from e
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file '{file_path}': {e}")
        raise FileReaderError("Failed to parse YAML file") from e
    except (IOError, OSError, PermissionError) as e:
        logger.error(f"Failed to read YAML file '{file_path}': {e}")
        raise FileReaderError("Failed to read YAML file") from e
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"Unexpected error reading YAML file '{file_path}': {error_type} - {e}")
        raise FileReaderError("Unexpected error reading YAML file") from e


# FileReaderクラスを削除し、直接関数を使用するように変更
# エイリアスとしての関数を追加（後方互換性のため）
def read_file(file_path: Path) -> str:
    """
    テキストファイルを読み込みます（read_markdown_fileと同じ動作）

    Args:
        file_path: 読み込むファイルのパス

    Returns:
        str: ファイルの内容

    Raises:
        FileReaderError: 読み込みエラー発生時
    """
    return read_markdown_file(file_path)


def read_yaml(file_path: Path) -> dict:
    """
    YAMLファイルを読み込みます（read_yaml_fileと同じ動作）

    Args:
        file_path: 読み込むYAMLファイルのパス

    Returns:
        dict: YAMLの内容を辞書として

    Raises:
        FileReaderError: 読み込みエラー発生時
    """
    return read_yaml_file(file_path)
