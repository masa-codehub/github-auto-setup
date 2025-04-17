import pytest
from unittest.mock import patch, MagicMock
import json
import logging  # caplog フィクスチャを使う場合
from pathlib import Path

# --- テスト対象のクラス、データモデル、例外をインポート ---
from github_automation_tool.adapters.ai_parser import AIParser
# ★ 更新されたモデルをインポート
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError
from github_automation_tool.infrastructure.config import Settings  # Settings も必要

# --- LangChain の型と例外 ---
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableSerializable
from langchain_core.exceptions import OutputParserException  # パースエラーテスト用

# --- API エラークラスのインポート試行とダミーインスタンス作成 (前回と同様) ---
try:
    from openai import AuthenticationError as OpenAIAuthenticationError, APIError, RateLimitError
    dummy_response_401 = MagicMock(status_code=401)
    dummy_body_401 = {"error": {"message": "Invalid API Key"}}
    API_AUTH_ERROR = OpenAIAuthenticationError(
        message="Invalid API Key", response=dummy_response_401, body=dummy_body_401)
except ImportError:
    API_AUTH_ERROR = ConnectionRefusedError("Simulated Auth Error")
    logging.warning(
        "openai library not found or outdated. Using fallback exceptions for testing.")

API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error")

try:
    from google.api_core.exceptions import PermissionDenied as GooglePermissionDenied
except ImportError:
    pass


# --- Fixtures (変更なし) ---
@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    settings.openai_api_key = MagicMock()
    settings.openai_api_key.get_secret_value.return_value = "fake-openai-key"
    settings.gemini_api_key = MagicMock()
    settings.gemini_api_key.get_secret_value.return_value = "fake-gemini-key"
    settings.ai_model = "openai"
    settings.log_level = "DEBUG"  # テスト中のログを見やすくするためDEBUGに設定
    return settings


@pytest.fixture
def mock_llm_chain() -> MagicMock:
    mock = MagicMock(spec=RunnableSerializable)
    mock.invoke = MagicMock()
    return mock


@pytest.fixture
def ai_parser(mock_settings: MagicMock, mock_llm_chain: MagicMock) -> AIParser:
    # AIParser の __init__ で _build_chain が呼ばれることを想定してパッチ
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain):
        parser = AIParser(settings=mock_settings)
        # テストからモックにアクセスできるよう設定
        parser.chain = mock_llm_chain
        return parser


# --- ★ 更新されたテストデータ ★ ---
SAMPLE_MARKDOWN_BASIC = """
---
**Title:** Basic Issue Title

**Description:** Just a description.
"""
# 基本ケースの期待値 (他のフィールドは空リスト or None)
EXPECTED_PARSED_DATA_BASIC = ParsedRequirementData(
    issues=[
        IssueData(title="Basic Issue Title", description="Just a description.", tasks=[], relational_definition=[
        ], relational_issues=[], acceptance=[], labels=None, milestone=None, assignees=None)
    ]
)

SAMPLE_MARKDOWN_FULL = """
---
**Title:** Full Feature Issue

**Description:** This issue has everything.

**Tasks:**
- Task 1
- Task 2

**関連要件:**
- REQ-001
- REQ-002

**関連Issue:**
- #123
- https://github.com/owner/repo/issues/456

**受け入れ基準:**
- AC 1 passed
- AC 2 checked

**Labels:** backend, feature, priority:high
**Milestone:** Sprint 1 Goals
**Assignee:** @developer1, @developer2
---
**Title:** Second Issue with Label only

**Description:** Minimal body.
**Labels:** frontend
"""
# フル情報ケースの期待値
EXPECTED_PARSED_DATA_FULL = ParsedRequirementData(
    issues=[
        IssueData(
            title="Full Feature Issue",
            description="**Description:** This issue has everything.",
            tasks=["Task 1", "Task 2"],
            relational_definition=["REQ-001", "REQ-002"],
            relational_issues=[
                "#123", "https://github.com/owner/repo/issues/456"],
            acceptance=["AC 1 passed", "AC 2 checked"],
            labels=["backend", "feature", "priority:high"],
            milestone="Sprint 1 Goals",
            assignees=["developer1", "developer2"]  # '@' なし
        ),
        IssueData(
            title="Second Issue with Label only",
            description="**Description:** Minimal body.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],  # 他は空リスト
            labels=["frontend"],  # ラベルのみあり
            milestone=None, assignees=None  # 他は None
        )
    ]
)

SAMPLE_MARKDOWN_NO_META = """
---
**Title:** Issue without extra meta

This is the main description.
- Including a task list style item
- Another item

This could be acceptance criteria.
"""
# メタ情報がないケースの期待値 (本文が description に入る想定)
EXPECTED_PARSED_DATA_NO_META = ParsedRequirementData(
    issues=[
        IssueData(
            title="Issue without extra meta",
            description="This is the main description.\n- Including a task list style item\n- Another item\n\nThis could be acceptance criteria.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],  # 他は空リスト
            labels=None, milestone=None, assignees=None  # メタ情報は None
        )
    ]
)


# --- Test Cases ---

def test_ai_parser_parse_success_basic(ai_parser: AIParser):
    """タイトルとDescriptionのみの基本的なIssueをパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_BASIC
    result = ai_parser.parse(SAMPLE_MARKDOWN_BASIC)
    assert result == EXPECTED_PARSED_DATA_BASIC
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.title == "Basic Issue Title"
    assert issue.description == "Just a description."
    assert issue.tasks == []
    assert issue.labels is None
    assert issue.milestone is None
    assert issue.assignees is None
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_BASIC})


def test_ai_parser_parse_success_full_info(ai_parser: AIParser):
    """ラベル、マイルストーン、担当者などフル情報を含むMarkdownを正常にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_FULL
    result = ai_parser.parse(SAMPLE_MARKDOWN_FULL)
    assert result == EXPECTED_PARSED_DATA_FULL  # オブジェクト全体を比較
    assert len(result.issues) == 2

    # 1つ目のIssueの詳細を確認
    issue1 = result.issues[0]
    assert issue1.title == "Full Feature Issue"
    assert issue1.description == "**Description:** This issue has everything."
    assert issue1.tasks == ["Task 1", "Task 2"]
    assert issue1.relational_definition == ["REQ-001", "REQ-002"]
    assert issue1.relational_issues == [
        "#123", "https://github.com/owner/repo/issues/456"]
    assert issue1.acceptance == ["AC 1 passed", "AC 2 checked"]
    assert issue1.labels == ["backend", "feature", "priority:high"]
    assert issue1.milestone == "Sprint 1 Goals"
    assert issue1.assignees == ["developer1", "developer2"]

    # 2つ目のIssueの詳細を確認
    issue2 = result.issues[1]
    assert issue2.title == "Second Issue with Label only"
    assert issue2.labels == ["frontend"]
    assert issue2.milestone is None  # 存在しないフィールドは None であることを確認
    assert issue2.assignees is None
    assert issue2.tasks == []  # デフォルトの空リストを確認

    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_FULL})


def test_ai_parser_parse_success_no_meta(ai_parser: AIParser):
    """ラベル等のメタ情報がないMarkdownを正常にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_NO_META
    result = ai_parser.parse(SAMPLE_MARKDOWN_NO_META)
    assert result == EXPECTED_PARSED_DATA_NO_META
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.title == "Issue without extra meta"
    # description に本文全体が入るか、あるいは空かはプロンプト次第
    # ここでは期待値オブジェクトに基づき検証
    assert issue.description == EXPECTED_PARSED_DATA_NO_META.issues[0].description
    assert issue.labels is None
    assert issue.milestone is None
    assert issue.assignees is None
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_NO_META})


def test_ai_parser_parse_empty_input(ai_parser: AIParser):  # 変更なし
    """空のMarkdownテキストが入力された場合、Chainは呼ばれずに空の結果が返るか"""
    empty_markdown = ""
    expected_empty_result = ParsedRequirementData(issues=[])
    result = ai_parser.parse(empty_markdown)
    assert result == expected_empty_result
    ai_parser.chain.invoke.assert_not_called()


def test_ai_parser_llm_api_authentication_error(ai_parser: AIParser):  # 変更なし
    """LLM APIで認証エラーが発生した場合に AiParserError (API Call Failed) が発生するか"""
    mock_api_error = API_AUTH_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    with pytest.raises(AiParserError, match="AI API call failed:") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error


# 変更なし (match文字列は修正済み)
def test_ai_parser_llm_api_timeout_error(ai_parser: AIParser):
    """LLM APIでタイムアウトエラーが発生した場合に AiParserError (Unexpected) が発生するか"""
    mock_api_error = API_TIMEOUT_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error


def test_ai_parser_output_parsing_error(ai_parser: AIParser):  # 変更なし
    """LLMが不正な形式のデータを返し、出力パースに失敗した場合 (OutputParserException)"""
    mock_parsing_error = OutputParserException("Failed to parse LLM output")
    ai_parser.chain.invoke.side_effect = mock_parsing_error
    with pytest.raises(AiParserError, match="Failed to parse AI output.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_parsing_error


def test_ai_parser_unexpected_error(ai_parser: AIParser):  # 変更なし
    """その他の予期せぬエラーが発生した場合"""
    mock_unexpected_error = ValueError("Something completely unexpected.")
    ai_parser.chain.invoke.side_effect = mock_unexpected_error
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_unexpected_error
