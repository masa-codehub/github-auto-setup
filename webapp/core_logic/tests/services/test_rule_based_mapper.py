"""
RuleBasedMapperService 単体テスト
"""
import pytest
from core_logic.services.rule_based_mapper import RuleBasedMapperService
from core_logic.domain.models import IssueData


@pytest.fixture
def default_mapping():
    return {
        "title": "Title",
        "description": "Description",
        "labels": "Labels",
        "labels__convert": "to_list_by_comma",
        "assignees": "Assignees",
        "assignees__convert": "extract_mentions",
    }


@pytest.fixture
def key_mapping_rule():
    return {
        "title": "件名",
        "description": "本文",
        "tasks": "タスク",
        "tasks__convert": "to_list_by_newline",
    }


@pytest.fixture
def block():
    return {
        "件名": "テストタイトル",
        "Title": "テストタイトル",  # default_mapping経由のtitle取得用
        "本文": "詳細説明",
        "Description": "詳細説明",  # default_mapping経由のdescription取得用
        "タスク": "タスク1\nタスク2",
        "Labels": "bug,feature",
        "Assignees": "@alice @bob"
    }


def test_map_block_to_issue_data_normal(default_mapping, key_mapping_rule, block):
    svc = RuleBasedMapperService(default_mapping)
    issue = svc.map_block_to_issue_data(block, key_mapping_rule)
    assert issue.title == "テストタイトル"
    assert issue.description == "詳細説明"
    assert issue.tasks == ["タスク1", "タスク2"]
    assert issue.labels == ["bug", "feature"]
    assert issue.assignees == ["alice", "bob"]


def test_title_required(default_mapping, key_mapping_rule, block):
    svc = RuleBasedMapperService(default_mapping)
    b = block.copy()
    b["件名"] = ""
    with pytest.raises(ValueError):
        svc.map_block_to_issue_data(b, key_mapping_rule)


def test_fallback_to_default_mapping(default_mapping, block):
    svc = RuleBasedMapperService(default_mapping)
    # key_mapping_ruleにtitleがない場合、default_mappingが使われる
    issue = svc.map_block_to_issue_data(block, {})
    assert issue.title == block["Title"]


def test_warning_on_missing_fields(default_mapping, key_mapping_rule, block, caplog):
    svc = RuleBasedMapperService(default_mapping)
    b = block.copy()
    b.pop("タスク")
    with caplog.at_level("WARNING"):
        issue = svc.map_block_to_issue_data(b, key_mapping_rule)
    assert "マッピング失敗: tasks" in caplog.text


def test_convert_error_logged(default_mapping, key_mapping_rule, block, caplog):
    svc = RuleBasedMapperService(default_mapping)
    b = block.copy()
    b["タスク"] = None  # to_list_by_newlineに不正値
    with caplog.at_level("WARNING"):
        issue = svc.map_block_to_issue_data(b, key_mapping_rule)
    assert "マッピング失敗: tasks" in caplog.text or "変換失敗: tasks" in caplog.text
