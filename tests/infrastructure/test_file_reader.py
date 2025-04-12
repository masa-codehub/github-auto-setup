import pytest
from pathlib import Path
import sys
import os
import subprocess
from unittest import mock

# モジュールをインポート (パスは環境に合わせて調整)
from github_automation_tool.infrastructure.file_reader import read_markdown_file

# --- Test Cases ---


def test_read_markdown_file_success(tmp_path: Path):
    """正常にUTF-8のMarkdownファイルの内容を読み込めるか"""
    content = "# テスト Title\n\nこれはテスト内容です。\n- item1\n- item2"
    file_path = tmp_path / "test_success.md"
    file_path.write_text(content, encoding='utf-8')

    read_content = read_markdown_file(file_path)
    assert read_content == content


def test_read_file_not_found():
    """存在しないファイルを指定した場合に FileNotFoundError が発生するか"""
    non_existent_path = Path("./non_existent_file.md")  # 相対パスでもOK
    with pytest.raises(FileNotFoundError, match="File not found"):
        read_markdown_file(non_existent_path)

# Windows では chmod の挙動が異なるため、Linux/macOS 環境でのみ実行するマーク


@pytest.mark.skipif(sys.platform == "win32", reason="chmod tests often fail on Windows")
def test_read_permission_error(tmp_path: Path):
    """読み取り権限のないファイルを指定した場合に PermissionError が発生するか"""
    file_path = tmp_path / "no_read_access.md"
    file_path.write_text("secret content", encoding='utf-8')

    # os.accessをモックして、アクセス権限がないように見せかける
    with mock.patch('os.access', return_value=False):
        with pytest.raises(PermissionError, match="Permission denied"):
            read_markdown_file(file_path)


def test_read_encoding_error(tmp_path: Path):
    """UTF-8として不正なファイル (例: Shift-JIS) を読み込もうとした場合に UnicodeDecodeError が発生するか"""
    file_path = tmp_path / "shift_jis_encoded.md"
    try:
        # Shift_JIS でエンコードされたバイト列
        content_bytes = "テスト文字列".encode('shift_jis')
        file_path.write_bytes(content_bytes)
    except LookupError:
        # 環境によってはスキップ
        pytest.skip("Shift_JIS codec not available on this system.")

    with pytest.raises(UnicodeDecodeError):
        read_markdown_file(file_path)


def test_read_directory_error(tmp_path: Path):
    """ファイルではなくディレクトリを指定した場合に FileNotFoundError が発生するか"""
    with pytest.raises(FileNotFoundError, match="is not a file"):  # is_file()がFalseになる
        read_markdown_file(tmp_path)
