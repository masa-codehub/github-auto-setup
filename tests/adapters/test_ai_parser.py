import pytest
from unittest.mock import MagicMock, patch
import os
import logging
# Pydanticのバージョンに合わせてインポート
from pydantic_core import ValidationError, PydanticCustomError
from pydantic import SecretStr  # SecretStrをインポート
from typing import Any, Dict, List, Optional, cast
# 正しいケースでインポート（AiParserError）
from github_automation_tool.domain.exceptions import AiParserError

from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.domain.models import ParsedRequirementData, IssueData

from github_automation_tool.infrastructure.config import Settings, AiSettings, LoggingSettings

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
        NotFoundError as OpenAINotFoundError, 
        APITimeoutError as OpenAITimeoutError
    )
    # モックエラーレスポンスの作成
    dummy_response_404 = MagicMock(status_code=404)
    dummy_body_404 = {"error": {"message": "The model `invalid-model` does not exist", "type": "invalid_request_error"}}
    API_INVALID_MODEL_ERROR_OPENAI = OpenAINotFoundError(
        message="Model not found", response=dummy_response_404, body=dummy_body_404
    )
    # 認証エラーの作成
    dummy_response_401 = MagicMock(status_code=401)
    dummy_body_401 = {"error": {"message": "Invalid API Key"}}
    API_AUTH_ERROR = OpenAIAuthenticationError(
        message="Invalid API Key", response=dummy_response_401, body=dummy_body_401)
except ImportError:
    # OpenAIライブラリがない場合はフォールバックエラークラスを使用
    API_INVALID_MODEL_ERROR_OPENAI = ConnectionRefusedError("Simulated OpenAI Model Not Found Error")
    API_AUTH_ERROR = ConnectionRefusedError("Simulated Auth Error")
    logging.warning("openai library not found or outdated. Using fallback exceptions for testing.")

# タイムアウトエラー
API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error")

# Google AI関連のエラーも同様に試行
try:
    from google.api_core.exceptions import (
        PermissionDenied as GooglePermissionDenied,
        NotFound as GoogleNotFound
    )
    API_INVALID_MODEL_ERROR_GOOGLE = GoogleNotFound("Simulated Google Model Not Found Error")
except ImportError:
    # Googleライブラリがない場合はフォールバックエラークラスを使用
    GooglePermissionDenied = ConnectionRefusedError("Simulated Google Permission Error")
    API_INVALID_MODEL_ERROR_GOOGLE = ConnectionRefusedError("Simulated Google Model Not Found Error")


# --- Fixtures ---
@pytest.fixture
def mock_settings() -> MagicMock:
    """テスト用の Settings モック (YAML読み込み後の想定)"""
    settings = MagicMock(spec=Settings)

    # --- 修正: ネストされたモデルとプロパティを模倣 ---
    # AiSettings のモック
    ai_settings_mock = MagicMock(spec=AiSettings)
    ai_settings_mock.openai_model_name = "gpt-4o" # デフォルト値
    ai_settings_mock.gemini_model_name = "gemini-1.5-flash" # デフォルト値
    ai_settings_mock.prompt_template = "Mock prompt template {format_instructions} for {markdown_text}" # テスト用テンプレート
    settings.ai = ai_settings_mock

    # LoggingSettings のモック
    logging_settings_mock = MagicMock(spec=LoggingSettings)
    logging_settings_mock.log_level = "INFO"
    settings.logging = logging_settings_mock

    # 環境変数由来のフィールド (デフォルトは None)
    settings.github_pat = SecretStr("fake-pat")
    settings.ai_model = "openai"
    settings.openai_api_key = SecretStr("fake-openai-key")
    settings.gemini_api_key = SecretStr("fake-gemini-key")
    settings.env_openai_model_name = None
    settings.env_gemini_model_name = None
    settings.env_log_level = None

    # 最終的な設定値を取得するプロパティもモック
    # (テストケース側で必要に応じてこれらの値を上書きする)
    settings.final_openai_model_name = ai_settings_mock.openai_model_name
    settings.final_gemini_model_name = ai_settings_mock.gemini_model_name
    settings.final_log_level = logging_settings_mock.log_level
    settings.prompt_template = ai_settings_mock.prompt_template
    # -----------------------------------------------

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
@pytest.mark.parametrize("model_type, env_model_name, yaml_model_name, expected_model_param_key, expected_model_name_used", [
    # OpenAI: Env override YAML
    ("openai", "gpt-4-env", "gpt-4-yaml", "model_name", "gpt-4-env"),
    # OpenAI: Env only (YAML default)
    ("openai", "gpt-4-env", "gpt-4o", "model_name", "gpt-4-env"),
    # OpenAI: YAML only (Env None)
    ("openai", None, "gpt-4-yaml", "model_name", "gpt-4-yaml"),
    # OpenAI: Neither (YAML default)
    ("openai", None, "gpt-4o", "model_name", "gpt-4o"),
    # Gemini: Env override YAML
    ("gemini", "gemini-1.5-env", "gemini-pro-yaml", "model", "gemini-1.5-env"),
    # Gemini: Env only (YAML default)
    ("gemini", "gemini-1.5-env", "gemini-1.5-flash", "model", "gemini-1.5-env"),
    # Gemini: YAML only (Env None)
    ("gemini", None, "gemini-pro-yaml", "model", "gemini-pro-yaml"),
    # Gemini: Neither (YAML default)
    ("gemini", None, "gemini-1.5-flash", "model", "gemini-1.5-flash"),
])
@patch('github_automation_tool.adapters.ai_parser.ChatOpenAI', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI', autospec=True)
def test_ai_parser_initializes_correct_llm_with_model_name(
    mock_chat_google: MagicMock, mock_chat_openai: MagicMock,
    mock_settings: MagicMock, model_type: str, env_model_name: str | None, yaml_model_name: str,
    expected_model_param_key: str, expected_model_name_used: str # expected_fallback_model は不要になった
):
    """AIParserが設定/フォールバックから正しいモデル名を使用してLLMクライアントを初期化するか"""
    # Arrange: モック設定オブジェクトの値をテストケースに合わせて上書き
    mock_settings.ai_model = model_type
    mock_settings.env_openai_model_name = env_model_name if model_type == "openai" else None
    mock_settings.env_gemini_model_name = env_model_name if model_type == "gemini" else None
    # YAML由来のデフォルト値も設定 (AiSettingsモックの属性を上書き)
    mock_settings.ai.openai_model_name = yaml_model_name if model_type == "openai" else "gpt-4o"
    mock_settings.ai.gemini_model_name = yaml_model_name if model_type == "gemini" else "gemini-1.5-flash"
    # 最終的なモデル名を再計算してモックに設定
    mock_settings.final_openai_model_name = env_model_name if model_type == "openai" and env_model_name else mock_settings.ai.openai_model_name
    mock_settings.final_gemini_model_name = env_model_name if model_type == "gemini" and env_model_name else mock_settings.ai.gemini_model_name

    mock_chain = MagicMock() # _build_chain のモック

    # Act
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_chain):
        parser = AIParser(settings=mock_settings) # _initialize_llm が呼ばれる

    # Assert
    if model_type == "openai":
        mock_chat_openai.assert_called_once()
        _, kwargs = mock_chat_openai.call_args
        assert kwargs.get('openai_api_key') == "fake-openai-key"
        assert kwargs.get(expected_model_param_key) == expected_model_name_used
        mock_chat_google.assert_not_called()
    elif model_type == "gemini":
        mock_chat_google.assert_called_once()
        _, kwargs = mock_chat_google.call_args
        assert kwargs.get('google_api_key') == "fake-gemini-key"
        assert kwargs.get(expected_model_param_key) == expected_model_name_used
        mock_chat_openai.assert_not_called()

# --- 無効なモデル名のエラーハンドリングテスト ---
@pytest.mark.parametrize("model_type, invalid_model_name, mock_api_error_class", [
    ("openai", "invalid-openai-model", API_INVALID_MODEL_ERROR_OPENAI),
    ("gemini", "invalid-gemini-model", API_INVALID_MODEL_ERROR_GOOGLE),
])
@patch('github_automation_tool.adapters.ai_parser.ChatOpenAI', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI', autospec=True)
def test_ai_parser_handles_invalid_model_name_on_init(
    mock_chat_google: MagicMock, mock_chat_openai: MagicMock,
    mock_settings: MagicMock, model_type: str, invalid_model_name: str, mock_api_error_class: Exception
):
    """無効なモデル名が設定された場合に初期化時にAiParserErrorが発生するか"""
    # Arrange
    mock_settings.ai_model = model_type
    if model_type == "openai":
        # 最終的なモデル名のプロパティを設定
        mock_settings.final_openai_model_name = invalid_model_name
        # LangChainクライアントの初期化時にAPIエラーが発生するようにモック
        mock_chat_openai.side_effect = mock_api_error_class
    else: # gemini
        # 最終的なモデル名のプロパティを設定
        mock_settings.final_gemini_model_name = invalid_model_name
        mock_chat_google.side_effect = mock_api_error_class

    # Act & Assert
    with pytest.raises(AiParserError, match="AI API Error during initialization") as excinfo:
        AIParser(settings=mock_settings)

    # 元の例外がラップされているか確認
    assert excinfo.value.original_exception is mock_api_error_class

# --- Parse Tests (prompt template 使用を反映) ---

# (サンプルMarkdownデータは変更なし)
# ...

def test_ai_parser_parse_success_basic(ai_parser: AIParser, mock_settings):
    """基本的なIssueをパースできるか"""
    expected_output = ParsedRequirementData(issues=[IssueData(title="Basic Issue", description="Desc")])
    ai_parser.chain.invoke.return_value = expected_output
    markdown_input = "Basic markdown"
    result = ai_parser.parse(markdown_input)
    assert result == expected_output
    # _build_chain が正しいテンプレートで呼ばれたかは __init__ で検証済み
    # invoke が正しい引数で呼ばれたかを確認
    ai_parser.chain.invoke.assert_called_once_with({"markdown_text": markdown_input})
    # _build_chain 内の PromptTemplate が設定のテンプレートを使うことを確認 (オプション)
    # これは _build_chain の単体テストの方が適切かもしれない

def test_build_chain_uses_settings_template(mock_settings):
    """_build_chain が settings のプロンプトテンプレートを使用するか"""
    mock_settings.ai.prompt_template = "Template: {markdown_text} / {format_instructions}"
    mock_settings.prompt_template = "Template: {markdown_text} / {format_instructions}" # プロパティも更新

    # LLMのモックを作成
    mock_llm = MagicMock(spec=BaseChatModel)
    # _initialize_llm をモックして、このLLMを返すようにする
    with patch('github_automation_tool.adapters.ai_parser.AIParser._initialize_llm', return_value=mock_llm):
         # PydanticOutputParser のモック (get_format_instructions を持つ)
         with patch('github_automation_tool.adapters.ai_parser.PydanticOutputParser') as mock_parser_cls:
             mock_parser_instance = MagicMock()
             mock_parser_instance.get_format_instructions.return_value = "FORMAT_INSTR"
             mock_parser_cls.return_value = mock_parser_instance

             # PromptTemplate のコンストラクタ呼び出しを捕捉するためのパッチ
             with patch('github_automation_tool.adapters.ai_parser.PromptTemplate') as mock_prompt_template:
                  parser = AIParser(settings=mock_settings) # _build_chain が呼ばれる

                  # PromptTemplate が期待通り呼ばれたか検証
                  mock_prompt_template.assert_called_once()
                  _, kwargs = mock_prompt_template.call_args
                  # settings から読み込んだテンプレートが渡されているか
                  assert kwargs.get('template') == "Template: {markdown_text} / {format_instructions}"
                  assert kwargs.get('input_variables') == ["markdown_text"]
                  assert kwargs.get('partial_variables') == {"format_instructions": "FORMAT_INSTR"}


def test_build_chain_raises_error_if_template_missing(mock_settings):
    """プロンプトテンプレートが設定にない場合に _build_chain がエラーを出すか"""
    # settings からプロンプトテンプレートを削除（または空にする）
    mock_settings.ai.prompt_template = ""
    mock_settings.prompt_template = ""

    mock_llm = MagicMock(spec=BaseChatModel)
    with patch('github_automation_tool.adapters.ai_parser.AIParser._initialize_llm', return_value=mock_llm):
        with pytest.raises(AiParserError, match="Prompt template is missing or empty"):
            # __init__ の中で _build_chain が呼ばれてエラーになる
            AIParser(settings=mock_settings)


# (その他の parse テストケースは変更なし、ai_parser フィクスチャが更新されたsettingsを使う)
# ...

# --- 追加: 空の結果に対する警告ログと ValidationError のテスト ---
def test_parse_with_empty_result(ai_parser: AIParser, caplog):
    """LLM が空の結果を返した場合、適切な警告ログが出力されるか"""
    # 空のissuesリストを返すようにモック設定
    empty_result = ParsedRequirementData(issues=[])
    ai_parser.chain.invoke.return_value = empty_result
    
    with caplog.at_level(logging.WARNING):
        result = ai_parser.parse("Some markdown text")
    
    # 警告ログが出力されたか検証
    assert "AI parsing finished, but no issues were extracted from the provided Markdown" in caplog.text
    # 空の結果が正しく返されたか検証
    assert result == empty_result
    assert len(result.issues) == 0

def test_parse_with_validation_error(ai_parser: AIParser):
    """LLM 出力が ValidationError を発生させた場合、AiParserError が発生するか"""
    # コンテンツからValidationErrorを発生させる
    # chain.invokeが例外を発生させるようにモックする
    validation_error = ValidationError.from_exception_data(
        title="ValidationError",
        line_errors=[{
            "type": "missing",
            "loc": ["title"],
            "msg": "Field required",
            "input": {}
        }]
    )
    ai_parser.chain.invoke.side_effect = validation_error
    
    # テスト - パースでエラーが発生すること
    with pytest.raises(AiParserError) as excinfo:
        ai_parser.parse("dummy content")
    
    # エラーメッセージが適切かチェック
    error_message = str(excinfo.value)
    assert "validation" in error_message.lower() or "AI output" in error_message

def test_parse_with_empty_markdown(ai_parser: AIParser, caplog):
    """空のマークダウン入力に対して、空の結果を返すか"""
    with caplog.at_level(logging.WARNING):
        result = ai_parser.parse("")
    
    # 警告ログが出力されたか検証
    assert "Input markdown text is empty or whitespace only" in caplog.text
    # 空のリストが返されたか検証
    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 0
    # 実際に LLM が呼び出されなかったことを検証
    ai_parser.chain.invoke.assert_not_called()


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
