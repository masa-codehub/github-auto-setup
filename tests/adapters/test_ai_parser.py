import pytest
from unittest.mock import patch, MagicMock, call # call を追加
import json
import logging
from pathlib import Path
from pydantic import SecretStr

# --- テスト対象のクラス、データモデル、例外をインポート ---
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError
from github_automation_tool.infrastructure.config import Settings

# --- LangChain の型と例外 ---
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableSerializable
from langchain_core.exceptions import OutputParserException

# --- API エラークラスのインポート試行とダミーインスタンス作成 ---
try:
    # openai >= 1.0.0
    from openai import (
        AuthenticationError as OpenAIAuthenticationError,
        APIError as OpenAIAPIError,
        RateLimitError as OpenAIRateLimitError,
        NotFoundError as OpenAINotFoundError, # 無効なモデル名用
        APITimeoutError as OpenAITimeoutError # タイムアウト用
    )
    # 無効なモデル名を示すAPIエラーのモック
    dummy_response_404 = MagicMock(status_code=404)
    dummy_body_404 = {"error": {"message": "The model `invalid-model` does not exist", "type": "invalid_request_error"}}
    API_INVALID_MODEL_ERROR_OPENAI = OpenAINotFoundError(
        message="Model not found", response=dummy_response_404, body=dummy_body_404
    )
    # 認証エラー
    dummy_response_401 = MagicMock(status_code=401)
    dummy_body_401 = {"error": {"message": "Invalid API Key"}}
    API_AUTH_ERROR = OpenAIAuthenticationError(
        message="Invalid API Key", response=dummy_response_401, body=dummy_body_401)
except ImportError:
    API_INVALID_MODEL_ERROR_OPENAI = ConnectionRefusedError("Simulated OpenAI Model Not Found Error")
    API_AUTH_ERROR = ConnectionRefusedError("Simulated Auth Error")
    logging.warning("openai library not found or outdated. Using fallback exceptions for testing.")

# タイムアウトエラー
API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error")

# Google AI関連のエラーも同様に試行
try:
    from google.api_core.exceptions import (
        PermissionDenied as GooglePermissionDenied,
        NotFound as GoogleNotFound # 無効なモデル名用
    )
    API_INVALID_MODEL_ERROR_GOOGLE = GoogleNotFound("Simulated Google Model Not Found Error")
except ImportError:
    GooglePermissionDenied = ConnectionRefusedError("Simulated Google Permission Error")
    API_INVALID_MODEL_ERROR_GOOGLE = ConnectionRefusedError("Simulated Google Model Not Found Error")


# --- Fixtures ---
@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    openai_key_mock = MagicMock()
    openai_key_mock.get_secret_value.return_value = "fake-openai-key"
    gemini_key_mock = MagicMock()
    gemini_key_mock.get_secret_value.return_value = "fake-gemini-key"
    settings.openai_api_key = openai_key_mock
    settings.gemini_api_key = gemini_key_mock
    settings.ai_model = "openai"
    settings.openai_model_name = None # デフォルトは None
    settings.gemini_model_name = None # デフォルトは None
    settings.log_level = "info"
    return settings

@pytest.fixture
def mock_llm_chain() -> MagicMock:
    mock = MagicMock(spec=RunnableSerializable)
    mock.invoke = MagicMock()
    return mock

@pytest.fixture
def ai_parser_no_init_llm(mock_settings: MagicMock, mock_llm_chain: MagicMock) -> AIParser:
    """AIParserを初期化するが、LLM初期化 (_initialize_llm) はモックしないフィクスチャ"""
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain):
        parser = AIParser(settings=mock_settings)
        parser.chain = mock_llm_chain
    return parser

@pytest.fixture
def ai_parser(mock_settings: MagicMock, mock_llm_chain: MagicMock) -> AIParser:
    """テスト用のAIParserインスタンス（LLM初期化とChain構築をモック）"""
    with patch('github_automation_tool.adapters.ai_parser.AIParser._initialize_llm') as mock_init_llm, \
         patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain) as mock_build_chain:
        mock_llm_instance = MagicMock(spec=BaseChatModel)
        mock_init_llm.return_value = mock_llm_instance
        parser = AIParser(settings=mock_settings)
        parser.llm = mock_llm_instance
        parser.chain = mock_llm_chain
        return parser

# --- AI モデル切り替えと初期化テスト (修正) ---
@pytest.mark.parametrize("model_type, model_name_setting, expected_model_param_key, expected_model_name_used, expected_fallback_model", [
    # OpenAI: 設定あり
    ("openai", "gpt-4-turbo", "model_name", "gpt-4-turbo", "gpt-4o"),
    # OpenAI: 設定なし (フォールバック)
    ("openai", None, "model_name", "gpt-4o", "gpt-4o"),
    # Gemini: 設定あり
    ("gemini", "gemini-1.5-pro", "model", "gemini-1.5-pro", "gemini-2.0-flash"),
    # Gemini: 設定なし (フォールバック)
    ("gemini", None, "model", "gemini-2.0-flash", "gemini-2.0-flash"),
])
@patch('github_automation_tool.adapters.ai_parser.ChatOpenAI', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI', autospec=True)
def test_ai_parser_initializes_correct_llm_with_model_name(
    mock_chat_google: MagicMock, mock_chat_openai: MagicMock, # patchデコレータの引数順
    mock_settings: MagicMock, model_type: str, model_name_setting: str | None,
    expected_model_param_key: str, expected_model_name_used: str, expected_fallback_model: str # 期待値の引数を修正
):
    """AIParserが設定/フォールバックから正しいモデル名を使用してLLMクライアントを初期化するか"""
    # Arrange
    mock_settings.ai_model = model_type
    if model_type == "openai":
        mock_settings.openai_model_name = model_name_setting
        mock_settings.gemini_model_name = None # 他方はNoneに
    else: # gemini
        mock_settings.gemini_model_name = model_name_setting
        mock_settings.openai_model_name = None

    mock_chain = MagicMock()

    # Act
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_chain):
        parser = AIParser(settings=mock_settings)

    # Assert
    if model_type == "openai":
        mock_chat_openai.assert_called_once()
        _, kwargs = mock_chat_openai.call_args
        assert kwargs.get('openai_api_key') == "fake-openai-key"
        # モデル名が期待通りか検証 (設定値またはフォールバック)
        assert kwargs.get(expected_model_param_key) == expected_model_name_used
        mock_chat_google.assert_not_called()
    elif model_type == "gemini":
        mock_chat_google.assert_called_once()
        _, kwargs = mock_chat_google.call_args
        assert kwargs.get('google_api_key') == "fake-gemini-key"
        # モデル名が期待通りか検証 (設定値またはフォールバック)
        assert kwargs.get(expected_model_param_key) == expected_model_name_used
        mock_chat_openai.assert_not_called()

# --- ★ 無効なモデル名のエラーハンドリングテストを追加 ★ ---
@pytest.mark.parametrize("model_type, invalid_model_name, mock_api_error_class", [
    ("openai", "invalid-openai-model", API_INVALID_MODEL_ERROR_OPENAI),
    ("gemini", "invalid-gemini-model", API_INVALID_MODEL_ERROR_GOOGLE),
])
@patch('github_automation_tool.adapters.ai_parser.ChatOpenAI', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI', autospec=True)
def test_ai_parser_handles_invalid_model_name_on_init(
    mock_chat_google: MagicMock, mock_chat_openai: MagicMock, # patchデコレータの引数順
    mock_settings: MagicMock, model_type: str, invalid_model_name: str, mock_api_error_class: Exception
):
    """無効なモデル名が設定された場合に初期化時にAiParserErrorが発生するか"""
    # Arrange
    mock_settings.ai_model = model_type
    if model_type == "openai":
        mock_settings.openai_model_name = invalid_model_name
        # LangChainクライアントの初期化時にAPIエラーが発生するようにモック
        mock_chat_openai.side_effect = mock_api_error_class
    else: # gemini
        mock_settings.gemini_model_name = invalid_model_name
        mock_chat_google.side_effect = mock_api_error_class

    # Act & Assert
    with pytest.raises(AiParserError, match="AI API Error during initialization") as excinfo:
        AIParser(settings=mock_settings)

    # 元の例外がラップされているか確認
    assert excinfo.value.original_exception is mock_api_error_class

# --- _build_chainのエラーハンドリングテスト ---
@patch('github_automation_tool.adapters.ai_parser.PydanticOutputParser', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.PromptTemplate', autospec=True)
def test_ai_parser_build_chain_exception(
    mock_prompt_template: MagicMock, mock_output_parser: MagicMock, mock_settings: MagicMock
):
    """_build_chainメソッド内で例外が発生した場合のテスト"""
    # 準備: _build_chainで使用される依存コンポーネントが例外を投げるようにモック
    mock_output_parser.side_effect = RuntimeError("Failed to create parser")
    
    # 実行と検証: AIParser初期化時に_build_chainが呼び出され、例外が発生する
    with patch('github_automation_tool.adapters.ai_parser.AIParser._initialize_llm') as mock_init_llm, \
         pytest.raises(AiParserError, match="Failed to build LangChain chain") as excinfo:
        mock_init_llm.return_value = MagicMock(spec=BaseChatModel)
        AIParser(settings=mock_settings)
    
    # 元の例外がラップされているか確認
    assert isinstance(excinfo.value.original_exception, RuntimeError)
    assert str(excinfo.value.original_exception) == "Failed to create parser"

def test_ai_parser_parse_result_type_error(ai_parser: AIParser):
    """parseメソッドがインスタンス型チェックに失敗した場合のテスト"""
    # 準備: LLMチェーンが期待されるParsedRequirementDataではなく別の型を返すようにモック
    ai_parser.chain.invoke.return_value = {"unexpected": "format"}
    
    # 実行と検証
    # AIParserErrorが発生し、最終的に「An unexpected error occurred during AI parsing.」というメッセージになることを期待
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing") as excinfo:
        ai_parser.parse("Some markdown text")
    
    # 元の例外がAiParserErrorであることを確認（二重ラップされている）
    original_exc = excinfo.value.original_exception
    assert isinstance(original_exc, AiParserError)
    assert "AI parsing resulted in unexpected data type" in str(original_exc)
    ai_parser.chain.invoke.assert_called_once_with({"markdown_text": "Some markdown text"})

# --- その他の予期せぬエラーをより詳細にテストするために例外種別を増やす ---
def test_ai_parser_parse_other_specific_exceptions(ai_parser: AIParser):
    """parseメソッドでキャッチされるその他の特殊な例外のテスト"""
    exceptions_to_test = [
        KeyError("Missing required key"),
        AssertionError("Validation failed"),
        MemoryError("Out of memory during processing"),
        TypeError("Type mismatch in operation")
    ]
    
    for exception in exceptions_to_test:
        # 設定: 毎回異なる例外を発生させる
        ai_parser.chain.invoke.side_effect = exception
        
        # 実行と検証
        with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing") as excinfo:
            ai_parser.parse("Some markdown text")
        
        assert excinfo.value.original_exception is exception

# --- 既存テストケース (変更なし、上記の ai_parser フィクスチャを使用) ---

SAMPLE_MARKDOWN_BASIC = """
---
**Title:** Basic Issue Title
**Description:** Just a description.
"""
EXPECTED_PARSED_DATA_BASIC = ParsedRequirementData(
    issues=[
        IssueData(title="Basic Issue Title", description="Just a description.", tasks=[], relational_definition=[], relational_issues=[], acceptance=[], labels=None, milestone=None, assignees=None)
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
EXPECTED_PARSED_DATA_FULL = ParsedRequirementData(
    issues=[
        IssueData(
            title="Full Feature Issue",
            description="This issue has everything.",
            tasks=["Task 1", "Task 2"],
            relational_definition=["REQ-001", "REQ-002"],
            relational_issues=["#123", "https://github.com/owner/repo/issues/456"],
            acceptance=["AC 1 passed", "AC 2 checked"],
            labels=["backend", "feature", "priority:high"],
            milestone="Sprint 1 Goals",
            assignees=["developer1", "developer2"]
        ),
        IssueData(
            title="Second Issue with Label only",
            description="Minimal body.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],
            labels=["frontend"],
            milestone=None, assignees=None
        )
    ]
)
SAMPLE_MARKDOWN_DIFFERENT_MILESTONES = """
---
**Title:** Issue with Milestone A
**Description:** This issue has milestone A.
**Milestone:** Sprint 1

---
**Title:** Issue with Milestone B
**Description:** This issue has milestone B.
**Milestone:** Sprint 2

---
**Title:** Issue with No Milestone
**Description:** This issue has no milestone.
"""
EXPECTED_PARSED_DATA_DIFFERENT_MILESTONES = ParsedRequirementData(
    issues=[
        IssueData(
            title="Issue with Milestone A",
            description="This issue has milestone A.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],
            labels=None,
            milestone="Sprint 1",
            assignees=None
        ),
        IssueData(
            title="Issue with Milestone B",
            description="This issue has milestone B.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],
            labels=None,
            milestone="Sprint 2",
            assignees=None
        ),
        IssueData(
            title="Issue with No Milestone",
            description="This issue has no milestone.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[],
            labels=None,
            milestone=None,
            assignees=None
        )
    ]
)


def test_ai_parser_parse_success_basic(ai_parser: AIParser):
    """基本的なIssueをパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_BASIC
    result = ai_parser.parse(SAMPLE_MARKDOWN_BASIC)
    assert result == EXPECTED_PARSED_DATA_BASIC
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_BASIC})

def test_ai_parser_parse_success_full_info(ai_parser: AIParser):
    """フル情報を含むMarkdownを正常にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_FULL
    result = ai_parser.parse(SAMPLE_MARKDOWN_FULL)
    assert result == EXPECTED_PARSED_DATA_FULL
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_FULL})

def test_ai_parser_parse_success_different_milestones(ai_parser: AIParser):
    """異なるマイルストーンを持つ複数のIssueを正確にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_DIFFERENT_MILESTONES
    result = ai_parser.parse(SAMPLE_MARKDOWN_DIFFERENT_MILESTONES)
    assert result == EXPECTED_PARSED_DATA_DIFFERENT_MILESTONES
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_DIFFERENT_MILESTONES})


def test_ai_parser_parse_empty_input(ai_parser: AIParser):
    """空のMarkdownテキストの場合"""
    empty_markdown = ""
    expected_empty_result = ParsedRequirementData(issues=[])
    result = ai_parser.parse(empty_markdown)
    assert result == expected_empty_result
    ai_parser.chain.invoke.assert_not_called()

def test_ai_parser_llm_api_authentication_error(ai_parser: AIParser):
    """LLM APIで認証エラー"""
    mock_api_error = API_AUTH_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    with pytest.raises(AiParserError, match="AI API call failed during parse") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error

def test_ai_parser_llm_api_timeout_error(ai_parser: AIParser):
    """LLM APIでタイムアウトエラー"""
    mock_api_error = API_TIMEOUT_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    # TimeoutErrorは OpenAI/Google のエラータプルに含まれていない場合があるので、
    # Unexpected error として捕捉される可能性がある
    expected_match = "AI API call failed during parse" if isinstance(mock_api_error, tuple(getattr(ai_parser, '_GOOGLE_ERRORS', ()) + getattr(ai_parser, '_OPENAI_ERRORS', ()))) else "An unexpected error occurred during AI parsing."
    with pytest.raises(AiParserError, match=expected_match) as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error

def test_ai_parser_output_parsing_error(ai_parser: AIParser):
    """LLM出力のパースエラー"""
    mock_parsing_error = OutputParserException("Failed to parse LLM output")
    ai_parser.chain.invoke.side_effect = mock_parsing_error
    with pytest.raises(AiParserError, match="Failed to parse AI output.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_parsing_error

def test_ai_parser_unexpected_error(ai_parser: AIParser):
    """その他の予期せぬエラー"""
    mock_unexpected_error = ValueError("Something completely unexpected.")
    ai_parser.chain.invoke.side_effect = mock_unexpected_error
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_unexpected_error
