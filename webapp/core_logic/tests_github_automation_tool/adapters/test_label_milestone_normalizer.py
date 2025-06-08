import pytest
from adapters.label_milestone_normalizer import LabelMilestoneNormalizerSvc


class DummyIssue:
    def __init__(self, labels=None, milestone=None):
        self.labels = labels
        self.milestone = milestone


def sample_label_defs():
    return [
        {"name": "type:bug", "aliases": ["バグ", "bug", "不具合"]},
        {"name": "type:feature", "aliases": ["feature", "新機能"]},
        {"name": "TDD", "aliases": ["TDD"]},
    ]


def sample_milestone_defs():
    return [
        {"name": "M2: AIパーサーコア機能実装とAPI詳細化", "aliases": ["M2", "AIパーサー"]},
        {"name": "M1: Web UI基礎とファイル処理API基盤", "aliases": ["M1"]},
    ]


def test_label_normalization_basic():
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(labels=["バグ", "feature", "TDD"])
    svc.normalize_issue(issue)
    assert set(issue.labels) == {"type:bug", "type:feature", "TDD"}


def test_label_normalization_case_and_alias():
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(labels=["BUG", "新機能", "tdd"])
    svc.normalize_issue(issue)
    assert set(issue.labels) == {"type:bug", "type:feature", "TDD"}


def test_label_normalization_unknown(caplog):
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(labels=["unknown", "バグ"])
    with caplog.at_level("WARNING"):
        svc.normalize_issue(issue)
    assert "未定義ラベル: 'unknown'" in caplog.text
    assert "type:bug" in issue.labels
    assert len(issue.labels) == 1


def test_milestone_normalization_basic():
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(milestone="M2")
    svc.normalize_issue(issue)
    assert issue.milestone == "M2: AIパーサーコア機能実装とAPI詳細化"


def test_milestone_normalization_case_and_alias():
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(milestone="aiパーサー")
    svc.normalize_issue(issue)
    assert issue.milestone == "M2: AIパーサーコア機能実装とAPI詳細化"


def test_milestone_normalization_unknown(caplog):
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(milestone="notfound")
    with caplog.at_level("WARNING"):
        svc.normalize_issue(issue)
    assert "未定義マイルストーン: 'notfound'" in caplog.text
    assert issue.milestone == "notfound"


def test_empty_labels_and_milestone():
    svc = LabelMilestoneNormalizerSvc(
        sample_label_defs(), sample_milestone_defs())
    issue = DummyIssue(labels=None, milestone=None)
    svc.normalize_issue(issue)
    assert issue.labels == []
    assert issue.milestone is None
