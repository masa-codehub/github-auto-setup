import sys
import os
import pytest

# sys.pathを調整し、プロジェクトルートをimportパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../../')))
from ..adapters.issue_file_parser_base import AbstractIssueFileParser, IntermediateParsingResult

class DummyParser(AbstractIssueFileParser):
    def parse(self, file_content: str) -> IntermediateParsingResult:
        return [file_content]

def test_abstract_issue_file_parser_cannot_instantiate():
    with pytest.raises(TypeError):
        AbstractIssueFileParser()

def test_dummy_parser_returns_input_as_list():
    parser = DummyParser()
    content = "sample issue text"
    result = parser.parse(content)
    assert isinstance(result, list)
    assert result == [content]
