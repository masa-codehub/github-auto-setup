from core_logic.adapters.markdown_issue_parser import MarkdownIssueParser


def test_parse_single_issue():
    content = """# Issue Title\nDescription of the issue."""
    parser = MarkdownIssueParser()
    result = parser.parse(content)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].strip() == content.strip()


def test_parse_multiple_issues_with_delimiter():
    content = """# Issue 1\nDesc 1\n---\n# Issue 2\nDesc 2\n---\n# Issue 3\nDesc 3"""
    parser = MarkdownIssueParser()
    result = parser.parse(content)
    assert len(result) == 3
    assert result[0].startswith("# Issue 1")
    assert result[1].startswith("# Issue 2")
    assert result[2].startswith("# Issue 3")


def test_parse_empty_file():
    parser = MarkdownIssueParser()
    result = parser.parse("")
    assert result == []


def test_parse_ignores_leading_and_trailing_delimiters():
    content = """---\n# Issue 1\nDesc\n---\n# Issue 2\nDesc\n---"""
    parser = MarkdownIssueParser()
    result = parser.parse(content)
    assert len(result) == 2
    assert all(block.strip().startswith("# Issue") for block in result)
