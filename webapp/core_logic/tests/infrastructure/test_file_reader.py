import pytest
import tempfile
import os
from pathlib import Path
from unittest import mock
import yaml
import logging
from core_logic.infrastructure.file_reader import (
    read_markdown_file, read_yaml_file, read_file, read_yaml, file_exists, FileReaderError
)


@pytest.fixture
def mock_file_path(tmp_path):
    """一時的なテストファイルを作成して返すフィクスチャ"""
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("test content")
    return file_path


@pytest.fixture
def mock_yaml_file_path(tmp_path):
    """一時的なYAMLファイルを作成して返すフィクスチャ"""
    content = {"key": "value", "nested": {"subkey": "subvalue"}}
    file_path = tmp_path / "test_file.yaml"
    with open(file_path, "w") as f:
        yaml.dump(content, f)
    return file_path


def test_read_file_success(mock_file_path):
    """ファイル読み取りが成功するケース"""
    result = read_markdown_file(mock_file_path)
    assert result == "test content"


def test_read_file_not_exists():
    """存在しないファイルを読み取ろうとして失敗するケース"""
    non_existent_path = Path("/non/existent/file.txt")

    with pytest.raises(FileReaderError, match="File not found"):
        read_markdown_file(non_existent_path)


def test_read_yaml_file_success(mock_yaml_file_path):
    """YAMLファイル読み取りが成功するケース"""
    result = read_yaml_file(mock_yaml_file_path)
    assert result["key"] == "value"
    assert result["nested"]["subkey"] == "subvalue"


def test_read_yaml_file_not_exists():
    """存在しないYAMLファイルを読み取ろうとして失敗するケース"""
    non_existent_path = Path("/non/existent/file.yaml")

    with pytest.raises(FileReaderError, match="YAML file not found"):
        read_yaml_file(non_existent_path)


def test_read_yaml_file_invalid_format(mock_file_path):
    """無効なYAML形式のファイルを読み取ろうとして失敗するケース"""
    with pytest.raises(FileReaderError, match="Failed to parse YAML file"):
        read_yaml_file(mock_file_path)


def test_file_exists_true(mock_file_path):
    """ファイルが存在する場合のテスト"""
    assert file_exists(mock_file_path) is True


def test_file_exists_false():
    """ファイルが存在しない場合のテスト"""
    non_existent_path = Path("/non/existent/file.txt")
    assert file_exists(non_existent_path) is False


def test_read_file_io_error(mock_file_path, caplog):
    """ファイル読み取り中にIOErrorが発生するケース"""
    # mockでPathオブジェクトのopen()が例外を発生させるようにする
    with mock.patch.object(Path, 'open', side_effect=IOError("Permission denied")):
        with pytest.raises(FileReaderError, match="Failed to read file"), caplog.at_level(logging.ERROR):
            read_markdown_file(mock_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Failed to read file" in caplog.text
        assert "Permission denied" in caplog.text


def test_read_file_os_error(mock_file_path, caplog):
    """ファイル読み取り中にOSErrorが発生するケース"""
    # mockでPathオブジェクトのopen()が例外を発生させるようにする
    with mock.patch.object(Path, 'open', side_effect=OSError("Too many open files")):
        with pytest.raises(FileReaderError, match="Failed to read file"), caplog.at_level(logging.ERROR):
            read_markdown_file(mock_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Failed to read file" in caplog.text
        assert "Too many open files" in caplog.text


def test_read_yaml_file_io_error(mock_yaml_file_path, caplog):
    """YAMLファイル読み取り中にIOErrorが発生するケース"""
    # mockでPathオブジェクトのopen()が例外を発生させるようにする
    with mock.patch.object(Path, 'open', side_effect=IOError("Permission denied")):
        with pytest.raises(FileReaderError, match="Failed to read YAML file"), caplog.at_level(logging.ERROR):
            read_yaml_file(mock_yaml_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Failed to read YAML file" in caplog.text
        assert "Permission denied" in caplog.text


def test_read_yaml_file_os_error(mock_yaml_file_path, caplog):
    """YAMLファイル読み取り中にOSErrorが発生するケース"""
    # mockでPathオブジェクトのopen()が例外を発生させるようにする
    with mock.patch.object(Path, 'open', side_effect=OSError("Too many open files")):
        with pytest.raises(FileReaderError, match="Failed to read YAML file"), caplog.at_level(logging.ERROR):
            read_yaml_file(mock_yaml_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Failed to read YAML file" in caplog.text
        assert "Too many open files" in caplog.text


def test_read_yaml_file_yaml_error(mock_yaml_file_path, caplog):
    """YAMLパース中にYAMLError発生するケース"""
    # open()は成功するが、yaml.safe_load()で例外が発生するように設定
    with mock.patch('yaml.safe_load', side_effect=yaml.YAMLError("Mapping values are not allowed here")):
        with pytest.raises(FileReaderError, match="Failed to parse YAML file"), caplog.at_level(logging.ERROR):
            read_yaml_file(mock_yaml_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Failed to parse YAML file" in caplog.text
        assert "Mapping values are not allowed here" in caplog.text


def test_read_yaml_file_unexpected_error(mock_yaml_file_path, caplog):
    """YAMLファイル読み取り中に予期せぬ例外が発生するケース"""
    # open()は成功するが、yaml.safe_load()で予期せぬ例外が発生
    with mock.patch('yaml.safe_load', side_effect=ValueError("Unexpected error")):
        with pytest.raises(FileReaderError, match="Unexpected error reading YAML file"), caplog.at_level(logging.ERROR):
            read_yaml_file(mock_yaml_file_path)

        # エラーログが適切に記録されていることを確認
        assert "Unexpected error reading YAML file" in caplog.text
        assert "ValueError" in caplog.text
        assert "Unexpected error" in caplog.text


# エイリアス関数のテスト
def test_read_file_alias(mock_file_path):
    """read_file関数がread_markdown_fileと同じ動作をするかテスト"""
    result = read_file(mock_file_path)
    assert result == "test content"

    # read_markdown_fileと同じ例外を発生させるか確認
    with mock.patch.object(Path, 'open', side_effect=IOError("Permission denied")):
        with pytest.raises(FileReaderError, match="Failed to read file"):
            read_file(mock_file_path)


def test_read_yaml_alias(mock_yaml_file_path):
    """read_yaml関数がread_yaml_fileと同じ動作をするかテスト"""
    result = read_yaml(mock_yaml_file_path)
    assert result["key"] == "value"
    assert result["nested"]["subkey"] == "subvalue"

    # read_yaml_fileと同じ例外を発生させるか確認
    with mock.patch.object(Path, 'open', side_effect=IOError("Permission denied")):
        with pytest.raises(FileReaderError, match="Failed to read YAML file"):
            read_yaml(mock_yaml_file_path)
