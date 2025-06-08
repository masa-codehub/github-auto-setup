import pytest
from core_logic.github_automation_tool.adapters.rule_based_splitter import RuleBasedSplitterSvc


@pytest.mark.parametrize("content, filetype, rule, expected", [
    ("""---\n**Title:** Issue1\n---\n**Title:** Issue2\n""", "md",
     {"type": "delimiter", "pattern": r"^---$"}, ["**Title:** Issue1", "**Title:** Issue2"]),
    ("""Title: Issue1\nBody: ...\nTitle: Issue2\nBody: ...\n""", "md", {
     "type": "leading_key", "key": "Title:"}, ["Title: Issue1\nBody: ...", "Title: Issue2\nBody: ..."]),
    ("""## Issue1\nBody\n## Issue2\nBody\n""", "md", {
     "type": "header_level", "level": 2}, ["## Issue1\nBody", "## Issue2\nBody"]),
    ("- title: Issue1\n  body: ...\n- title: Issue2\n  body: ...\n", "yaml", None, [
        {'title': 'Issue1', 'body': '...'}, {'title': 'Issue2', 'body': '...'}]),
    ('{"issues": [{"title": "Issue1"}, {"title": "Issue2"}]}', "json", None, [
        {'title': 'Issue1'}, {'title': 'Issue2'}]),
    ("", "md", None, []),
    ("", "yaml", None, []),
    ("", "json", None, []),
])
def test_rule_based_splitter(content, filetype, rule, expected):
    svc = RuleBasedSplitterSvc()
    result = svc.split(content, filetype, rule)
    if isinstance(expected, list) and expected and isinstance(expected[0], dict):
        # YAML/JSON: dictリスト
        assert isinstance(result, list)
        assert all(isinstance(x, dict) for x in result)
        assert len(result) == len(expected)
        for r, e in zip(result, expected):
            for k in e:
                assert r.get(k) == e[k]
    else:
        # Markdown: strリスト
        assert result == expected


def test_splitter_edge_cases():
    svc = RuleBasedSplitterSvc()
    # 区切り文字がない場合
    assert svc.split("No delimiter here", "md", {
                     "type": "delimiter", "pattern": r"^---$"}) == ["No delimiter here"]
    # YAML/JSONでリストが見つからない場合
    assert svc.split("key: value", "yaml") == []
    assert svc.split("{\"key\": \"value\"}", "json") == []


def test_split_yaml_logs_warning_on_invalid_yaml(caplog):
    svc = RuleBasedSplitterSvc()
    invalid_yaml = "- valid: 1\n  - invalid"  # インデント不正でパース失敗するYAML
    with caplog.at_level('WARNING'):
        result = svc._split_yaml(invalid_yaml)
    assert result == []
    assert any(
        "Failed to parse YAML content due to YAMLError" in record.message for record in caplog.records)
