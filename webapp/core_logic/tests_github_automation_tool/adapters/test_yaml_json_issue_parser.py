import pytest
import logging
from adapters.yaml_issue_parser import YamlIssueParser
from adapters.json_issue_parser import JsonIssueParser
from domain.exceptions import ParsingError


def test_parse_simple_yaml_list():
    content = """- title: Issue 1\n  desc: foo\n- title: Issue 2\n  desc: bar"""
    parser = YamlIssueParser()
    result = parser.parse(content)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["title"] == "Issue 1"


def test_parse_yaml_with_issues_key():
    content = """issues:\n  - title: A\n    desc: d1\n  - title: B\n    desc: d2"""
    parser = YamlIssueParser()
    result = parser.parse(content)
    assert len(result) == 2
    assert result[1]["title"] == "B"


def test_parse_yaml_empty():
    parser = YamlIssueParser()
    assert parser.parse("") == []


def test_parse_yaml_invalid():
    parser = YamlIssueParser()
    with pytest.raises(ParsingError):
        parser.parse("foo: [unclosed")


def test_parse_simple_json_list():
    content = '[{"title": "A"}, {"title": "B"}]'
    parser = JsonIssueParser()
    result = parser.parse(content)
    assert isinstance(result, list)
    assert result[0]["title"] == "A"


def test_parse_json_with_issues_key():
    content = '{"issues": [{"title": "A"}, {"title": "B"}]}'
    parser = JsonIssueParser()
    result = parser.parse(content)
    assert len(result) == 2
    assert result[1]["title"] == "B"


def test_parse_json_empty():
    parser = JsonIssueParser()
    assert parser.parse("") == []


def test_parse_json_invalid():
    parser = JsonIssueParser()
    with pytest.raises(ParsingError):
        parser.parse('{"foo": [}')


def test_yaml_no_issues_key_returns_empty():
    content = """foo:\n  - bar\nbar:\n  - baz"""
    parser = YamlIssueParser(issues_key="notfound")
    result = parser.parse(content)
    assert result == []


def test_json_no_issues_key_returns_empty():
    content = '{"foo": [{"x":1}], "bar": [{"y":2}]}'
    parser = JsonIssueParser(issues_key="notfound")
    result = parser.parse(content)
    assert result == []


def test_yaml_issues_key_value_not_a_list_logs_warning_and_returns_empty(caplog):
    parser = YamlIssueParser(issues_key="entries")
    content = """
entries: "this is not a list"
"""
    with caplog.at_level(logging.WARNING):
        result = parser.parse(content)
    assert result == []
    assert "Key 'entries' found in YAML but its value is not a list (type: str). Returning empty list." in caplog.text


def test_json_issues_key_value_not_a_list_logs_warning_and_returns_empty(caplog):
    parser = JsonIssueParser(issues_key="data_points")
    content = '{"data_points": {"item1": "value1"}}'
    with caplog.at_level(logging.WARNING):
        result = parser.parse(content)
    assert result == []
    assert "Key 'data_points' found in JSON but its value is not a list (type: dict). Returning empty list." in caplog.text
