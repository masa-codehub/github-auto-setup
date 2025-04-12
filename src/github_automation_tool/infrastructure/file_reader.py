import os
from pathlib import Path


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
        FileNotFoundError: If the file does not exist or is a directory.
        PermissionError: If read permission is denied.
        UnicodeDecodeError: If the file cannot be decoded as UTF-8.
        IOError/OSError: For other potential I/O errors during read.
    """
    if not file_path.is_file():
        if file_path.exists():
            raise FileNotFoundError(
                f"Path exists but is not a file: {file_path}")
        else:
            raise FileNotFoundError(f"File not found: {file_path}")

    if not os.access(file_path, os.R_OK):
        raise PermissionError(
            f"Permission denied when reading file: {file_path}")

    try:
        with file_path.open(mode='r', encoding='utf-8') as f:
            content = f.read()
        return content
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object,
                                 e.start, e.end, e.reason) from e
    except (IOError, OSError) as e:
        raise IOError(
            f"An I/O error occurred reading file '{file_path}': {e}") from e
