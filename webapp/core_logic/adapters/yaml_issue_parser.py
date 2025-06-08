from .issue_file_parser_base import AbstractIssueFileParser, IntermediateParsingResult
from core_logic.domain.exceptions import ParsingError
import yaml
import logging

logger = logging.getLogger(__name__)


class YamlIssueParser(AbstractIssueFileParser):
    """
    YAMLファイルからIssueブロック（辞書リスト）を抽出するパーサー。
    デフォルトでは'issues'キーを探索。見つからなければ空リストを返す。
    フォールバックで最初のリストを返す仕様は廃止。
    issues_keyが存在しても値がリストでなければ警告ログを出し空リストを返す。
    """

    def __init__(self, issues_key: str = "issues"):
        self.issues_key = issues_key

    def parse(self, file_content: str) -> IntermediateParsingResult:
        if not file_content or not file_content.strip():
            return []
        try:
            data = yaml.safe_load(file_content)
        except yaml.YAMLError as e:
            raise ParsingError(f"Invalid YAML format: {e}") from e
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if self.issues_key in data:
                issues_value = data[self.issues_key]
                if isinstance(issues_value, list):
                    return issues_value
                else:
                    logger.warning(
                        f"Key '{self.issues_key}' found in YAML but its value is not a list (type: {type(issues_value).__name__}). Returning empty list."
                    )
                    return []
        return []
