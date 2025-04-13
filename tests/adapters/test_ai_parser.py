import pytest
from unittest.mock import patch, MagicMock
import json
import logging # caplog フィクスチャを使う場合
from pathlib import Path

# --- テスト対象のクラス、データモデル、例外をインポート ---
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError
from github_automation_tool.infrastructure.config import Settings # Settings も必要

# --- LangChain の型と例外 ---
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableSerializable
from langchain_core.exceptions import OutputParserException # パースエラーテスト用

# --- API エラークラスのインポート試行とダミーインスタンス作成 ---
_OPENAI_ERRORS = tuple()
try:
    # ★ APITimeoutError のインポートを削除
    from openai import AuthenticationError as OpenAIAuthenticationError, APIError, RateLimitError

    # ダミーの response と body を作成
    dummy_response_401 = MagicMock()
    dummy_response_401.status_code = 401
    dummy_body_401 = {"error": {"message": "Invalid API Key", "type": "auth_error"}}
    # ★ 必須引数を渡してインスタンス化
    API_AUTH_ERROR = OpenAIAuthenticationError(
        message="Invalid API Key", response=dummy_response_401, body=dummy_body_401
    )
    # ★ Timeout は標準の TimeoutError を使う
    API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error")
    _OPENAI_ERRORS = (OpenAIAuthenticationError, RateLimitError, APIError) # タプルからも削除

except ImportError:
    # フォールバック
    API_AUTH_ERROR = ConnectionRefusedError("Simulated Auth Error - OpenAI lib not found")
    API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error - OpenAI lib not found")
    logging.warning("openai library not found or outdated. Using fallback exceptions for testing.")

# Google の例外も必要に応じて同様に確認・修正が必要
_GOOGLE_ERRORS = tuple()
try:
    from google.api_core.exceptions import PermissionDenied as GooglePermissionDenied
    from google.api_core.exceptions import ResourceExhausted as GoogleResourceExhausted
    from google.api_core.exceptions import GoogleAPICallError, DeadlineExceeded as GoogleTimeoutError
    _GOOGLE_ERRORS = (GooglePermissionDenied, GoogleResourceExhausted, GoogleAPICallError, GoogleTimeoutError)
except ImportError:
    pass


# --- Fixtures ---
@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    settings.openai_api_key = MagicMock()
    settings.openai_api_key.get_secret_value.return_value = "fake-openai-key"
    settings.gemini_api_key = MagicMock()
    settings.gemini_api_key.get_secret_value.return_value = "fake-gemini-key"
    settings.ai_model = "openai" # テストのデフォルト
    return settings

@pytest.fixture
def mock_llm_chain() -> MagicMock:
    mock = MagicMock(spec=RunnableSerializable)
    mock.invoke = MagicMock() # invokeもモックであることを明示
    return mock

@pytest.fixture
def ai_parser(mock_settings: MagicMock, mock_llm_chain: MagicMock) -> AIParser:
    # AIParserの内部実装に合わせて _build_chain をモック
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain):
         parser = AIParser(settings=mock_settings)
         # テストから Chain モックにアクセスできるようにインスタンス変数に入れる
         parser.chain = mock_llm_chain
         return parser

# --- Test Data ---
SAMPLE_MARKDOWN_SINGLE_ISSUE = """
---
**Title:** Implement Login Feature

**Description:** User should be able to login.
**Tasks:**
- [ ] Create endpoint
- [ ] Validate input
"""
EXPECTED_PARSED_DATA_SINGLE = ParsedRequirementData(
    issues=[IssueData(title="Implement Login Feature", body="**Description:** User should be able to login.\n**Tasks:**\n- [ ] Create endpoint\n- [ ] Validate input")]
)

SAMPLE_MARKDOWN_MULTIPLE_ISSUES = """
---
**Title:** First Issue

Body 1
---
**Title:** Second Issue

Body 2
Tasks:
- Task A
"""
EXPECTED_PARSED_DATA_MULTIPLE = ParsedRequirementData(
    issues=[
        IssueData(title="First Issue", body="Body 1"),
        IssueData(title="Second Issue", body="Body 2\nTasks:\n- Task A")
    ]
)


# --- Test Cases ---

def test_ai_parser_parse_success_single_issue(ai_parser: AIParser):
    """単一IssueのMarkdownを正常にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_SINGLE
    result = ai_parser.parse(SAMPLE_MARKDOWN_SINGLE_ISSUE)
    assert result == EXPECTED_PARSED_DATA_SINGLE
    ai_parser.chain.invoke.assert_called_once_with({"markdown_text": SAMPLE_MARKDOWN_SINGLE_ISSUE})

def test_ai_parser_parse_success_multiple_issues(ai_parser: AIParser):
    """複数IssueのMarkdownを正常にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_MULTIPLE
    result = ai_parser.parse(SAMPLE_MARKDOWN_MULTIPLE_ISSUES)
    assert result == EXPECTED_PARSED_DATA_MULTIPLE
    ai_parser.chain.invoke.assert_called_once_with({"markdown_text": SAMPLE_MARKDOWN_MULTIPLE_ISSUES})

def test_ai_parser_parse_empty_input(ai_parser: AIParser):
    """空のMarkdownテキストが入力された場合、Chainは呼ばれずに空の結果が返るか"""
    empty_markdown = ""
    expected_empty_result = ParsedRequirementData(issues=[])
    result = ai_parser.parse(empty_markdown)
    assert result == expected_empty_result
    ai_parser.chain.invoke.assert_not_called()

def test_ai_parser_llm_api_authentication_error(ai_parser: AIParser):
    """LLM APIで認証エラーが発生した場合に AiParserError (API Call Failed) が発生するか"""
    mock_api_error = API_AUTH_ERROR # 修正済みのエラーオブジェクトを使用
    ai_parser.chain.invoke.side_effect = mock_api_error
    with pytest.raises(AiParserError, match="AI API call failed:") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error

def test_ai_parser_llm_api_timeout_error(ai_parser: AIParser):
    """LLM APIでタイムアウトエラーが発生した場合に AiParserError (Unexpected) が発生するか"""
    # ★ side_effect に標準の TimeoutError を設定
    mock_api_error = API_TIMEOUT_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    # ★ ai_parser.py は TimeoutError を最後の except Exception で捕捉するため、match を修正
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error

def test_ai_parser_output_parsing_error(ai_parser: AIParser):
    """LLMが不正な形式のデータを返し、出力パースに失敗した場合 (OutputParserException)"""
    # ★ side_effect に OutputParserException を設定
    mock_parsing_error = OutputParserException("Failed to parse LLM output into Pydantic model.")
    ai_parser.chain.invoke.side_effect = mock_parsing_error
    # ★ match を ai_parser.py の except OutputParserException ブロックのメッセージに合わせる
    with pytest.raises(AiParserError, match="Failed to parse AI output.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_parsing_error

def test_ai_parser_unexpected_error(ai_parser: AIParser):
    """その他の予期せぬエラーが発生した場合"""
    # ★ side_effect に汎用 Exception を設定
    mock_unexpected_error = ValueError("Something completely unexpected.")
    ai_parser.chain.invoke.side_effect = mock_unexpected_error
    # ★ match を ai_parser.py の最後の except Exception ブロックのメッセージに合わせる
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_unexpected_error