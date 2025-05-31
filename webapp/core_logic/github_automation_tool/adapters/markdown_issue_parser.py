from .issue_file_parser_base import AbstractIssueFileParser, IntermediateParsingResult
from webapp.core_logic.github_automation_tool.domain.exceptions import ParsingError
import re

class MarkdownIssueParser(AbstractIssueFileParser):
    """
    MarkdownファイルからIssueブロックを抽出するパーサー。
    区切り文字の正規表現パターンをコンストラクタで指定可能。
    デフォルトでは行頭の '---' のみを区切り文字として扱います。
    将来的には、このパターンを設定ファイル (例: config.yaml) から
    供給することも検討可能です。
    """
    def __init__(self, delimiter_pattern: str = r"^---$"):
        self.delimiter_pattern = delimiter_pattern

    def parse(self, file_content: str) -> IntermediateParsingResult:
        if not file_content or not file_content.strip():
            return []
        # デフォルトは'---'のみ。将来的にre.splitで複数パターン対応可。
        blocks = [block.strip() for block in re.split(self.delimiter_pattern, file_content, flags=re.MULTILINE)]
        return [block for block in blocks if block]
