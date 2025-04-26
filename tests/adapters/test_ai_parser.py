import pytest
from unittest.mock import patch, MagicMock
import json
import logging  # caplog フィクスチャを使う場合
from pathlib import Path
from pydantic import SecretStr # SecretStr をインポート

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
    # API エラーのモックを作成（テストデータとして利用）
    dummy_response_401 = MagicMock(status_code=401)
    dummy_body_401 = {"error": {"message": "Invalid API Key"}}
    API_AUTH_ERROR = OpenAIAuthenticationError(
        message="Invalid API Key", response=dummy_response_401, body=dummy_body_401)
except ImportError:
    # ライブラリがない場合は代替エラーでテスト
    API_AUTH_ERROR = ConnectionRefusedError("Simulated Auth Error")
    logging.warning(
        "openai library not found or outdated. Using fallback exceptions for testing.")

API_TIMEOUT_ERROR = TimeoutError("Simulated Timeout Error")

# Google AI関連のエラーも同様に試行
try:
    from google.api_core.exceptions import PermissionDenied as GooglePermissionDenied
except ImportError:
    GooglePermissionDenied = ConnectionRefusedError("Simulated Google Permission Error") # フォールバック


# --- Fixtures ---
@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    
    # SecretStrのモックを正しく設定
    # 実際のSecretStrオブジェクトではなく、get_secret_valueメソッドを持つMockオブジェクトを作成
    openai_key_mock = MagicMock()
    openai_key_mock.get_secret_value.return_value = "fake-openai-key"
    
    gemini_key_mock = MagicMock()
    gemini_key_mock.get_secret_value.return_value = "fake-gemini-key"
    
    # Mockオブジェクトをsettingsの属性として設定
    settings.openai_api_key = openai_key_mock
    settings.gemini_api_key = gemini_key_mock
    settings.ai_model = "openai" # デフォルトは openai
    
    # model_name 属性を追加
    settings.openai_model_name = None
    settings.gemini_model_name = None
    
    # log_level 属性を追加
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
    # _build_chain のみをモックして、_initialize_llm は実際のコードが呼ばれるようにする
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain):
        # __init__ 内で _initialize_llm が呼ばれる
        parser = AIParser(settings=mock_settings)
        parser.chain = mock_llm_chain # chain はモックのまま
    return parser

@pytest.fixture
def ai_parser(mock_settings: MagicMock, mock_llm_chain: MagicMock) -> AIParser:
    """テスト用のAIParserインスタンス（LLM初期化とChain構築をモック）"""
    # _initialize_llm と _build_chain の両方をモック
    with patch('github_automation_tool.adapters.ai_parser.AIParser._initialize_llm') as mock_init_llm, \
         patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_llm_chain) as mock_build_chain:
        # モックされたLLMインスタンスを返すように設定
        mock_llm_instance = MagicMock(spec=BaseChatModel)
        mock_init_llm.return_value = mock_llm_instance

        parser = AIParser(settings=mock_settings)
        # テストからモックにアクセスできるよう設定
        parser.llm = mock_llm_instance
        parser.chain = mock_llm_chain
        return parser


# --- ★ AI モデル切り替えと初期化テスト ★ ---

# parametrize で openai と gemini のケースをテスト
# フォールバックモデル名の期待値を追加
@pytest.mark.parametrize("model_name, expected_llm_class_path, expected_api_key, expected_fallback_model", [
    ("openai", "github_automation_tool.adapters.ai_parser.ChatOpenAI", "fake-openai-key", "gpt-4o"),
    ("gemini", "github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI", "fake-gemini-key", "gemini-2.0-flash"),
])
# LangChain クライアントのコンストラクタをモック
@patch('github_automation_tool.adapters.ai_parser.ChatOpenAI', autospec=True)
@patch('github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI', autospec=True)
def test_ai_parser_initializes_correct_llm(
    mock_chat_google: MagicMock, mock_chat_openai: MagicMock, # patchデコレータの引数順に注意
    mock_settings: MagicMock, model_name: str, expected_llm_class_path: str, expected_api_key: str, expected_fallback_model: str # expected_fallback_model を追加
):
    """AIParserが設定に応じて正しいLLMクライアントを正しいAPIキーで初期化するか"""
    # Arrange: 設定の ai_model をパラメータに合わせて変更
    mock_settings.ai_model = model_name
    # Arrange: model_name を None に設定してフォールバックをテスト
    mock_settings.openai_model_name = None
    mock_settings.gemini_model_name = None
    # _build_chain はダミーで良いのでモック
    mock_chain = MagicMock()

    # Act: AIParser を初期化 (__init__内で _initialize_llm が呼ばれる)
    with patch('github_automation_tool.adapters.ai_parser.AIParser._build_chain', return_value=mock_chain):
        parser = AIParser(settings=mock_settings)

    # Assert: 期待されるLLMクラスのコンストラクタが呼ばれたか
    if model_name == "openai":
        mock_chat_openai.assert_called_once()
        # コンストラクタ呼び出しのキーワード引数を取得
        _, kwargs = mock_chat_openai.call_args
        assert kwargs.get('openai_api_key') == expected_api_key
        assert kwargs.get('temperature') == 0 # 他の引数も必要なら検証
        # フォールバックモデル名が使われることを確認
        assert kwargs.get('model_name') == expected_fallback_model
        mock_chat_google.assert_not_called() # Gemini は呼ばれない
        assert isinstance(parser.llm, MagicMock) # モックされたインスタンスが設定されている
    elif model_name == "gemini":
        mock_chat_google.assert_called_once()
        _, kwargs = mock_chat_google.call_args
        assert kwargs.get('google_api_key') == expected_api_key
        # フォールバックモデル名が使われることを確認
        assert kwargs.get('model') == expected_fallback_model
        assert kwargs.get('temperature') == 0
        assert kwargs.get('convert_system_message_to_human') is True
        mock_chat_openai.assert_not_called() # OpenAI は呼ばれない
        assert isinstance(parser.llm, MagicMock)

@pytest.mark.parametrize("model_name, missing_library_class_path", [
    ("openai", "github_automation_tool.adapters.ai_parser.ChatOpenAI"),
    ("gemini", "github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI"),
])
def test_ai_parser_handles_import_error(
    mock_settings: MagicMock, model_name: str, missing_library_class_path: str
):
    """対応するLangChainライブラリがない場合にAiParserErrorを発生させるか"""
    # Arrange: 設定の ai_model を設定
    mock_settings.ai_model = model_name
    # Arrange: patch を使って対象クラスを None にし、ImportError をシミュレート
    with patch(missing_library_class_path, None):
        # Act & Assert: AiParserError が発生し、メッセージにライブラリ名が含まれるか
        with pytest.raises(AiParserError, match=f"Required library not installed for '{model_name}'"):
            AIParser(settings=mock_settings)

@pytest.mark.parametrize("model_name, missing_key_attr", [
    ("openai", "openai_api_key"),
    ("gemini", "gemini_api_key"),
])
def test_ai_parser_handles_missing_api_key(
    mock_settings: MagicMock, model_name: str, missing_key_attr: str
):
    """必要なAPIキーが設定にない場合にAiParserErrorを発生させるか"""
    # Arrange: 設定の ai_model を設定
    mock_settings.ai_model = model_name
    # Arrange: 該当する API キーを None に設定
    setattr(mock_settings, missing_key_attr, None)
    # または空の SecretStr
    # setattr(mock_settings, missing_key_attr, SecretStr(""))

    # Act & Assert: AiParserError が発生し、メッセージにエラー内容が含まれるか
    with pytest.raises(AiParserError, match=f"Configuration error for \'{model_name}\'") as excinfo:
        AIParser(settings=mock_settings)
    # エラーメッセージの詳細も確認できるとより良い
    # 実際のエラーメッセージに合わせてアサーションを修正
    assert "API Key is required but missing in settings" in str(excinfo.value)


def test_ai_parser_handles_unsupported_model(mock_settings: MagicMock):
    """サポートされていないai_modelが指定された場合にAiParserErrorを発生させるか"""
    # Arrange: サポートされていないモデル名を設定
    unsupported_model = "unsupported-ai-service"
    mock_settings.ai_model = unsupported_model

    # Act & Assert: AiParserError が発生し、メッセージにモデル名が含まれるか
    with pytest.raises(AiParserError, match=f"Unsupported AI model type: '{unsupported_model}'"):
        AIParser(settings=mock_settings)


# --- ★ 更新されたテストデータ ★ ---
SAMPLE_MARKDOWN_BASIC = """
---
**Title:** Basic Issue Title
**Description:** Just a description.
"""
# 基本ケースの期待値 (他のフィールドは空リスト or None)
EXPECTED_PARSED_DATA_BASIC = ParsedRequirementData(
    issues=[
        IssueData(title="Basic Issue Title", description="Just a description.", tasks=[], relational_definition=[], relational_issues=[], acceptance=[], labels=None, milestone=None, assignees=None)
    ]
)

# 異なるマイルストーンを持つIssueのテストデータを追加
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

# 異なるマイルストーンを持つIssueの期待値
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
# フル情報ケースの期待値 (Pydantic モデルに合わせて修正)
EXPECTED_PARSED_DATA_FULL = ParsedRequirementData(
    issues=[
        IssueData(
            title="Full Feature Issue",
            description="This issue has everything.", # Description部分のみ抽出される想定
            tasks=["Task 1", "Task 2"],
            relational_definition=["REQ-001", "REQ-002"],
            relational_issues=["#123", "https://github.com/owner/repo/issues/456"],
            acceptance=["AC 1 passed", "AC 2 checked"],
            labels=["backend", "feature", "priority:high"],
            milestone="Sprint 1 Goals",
            assignees=["developer1", "developer2"]  # '@' なし
        ),
        IssueData(
            title="Second Issue with Label only",
            description="Minimal body.", # Description部分のみ抽出される想定
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
# メタ情報がないケースの期待値 (本文が description に入る想定、Pydanticに合わせて修正)
EXPECTED_PARSED_DATA_NO_META = ParsedRequirementData(
    issues=[
        IssueData(
            title="Issue without extra meta",
            # AI Parserの実装によるが、descriptionフィールドがない場合は本文全体を抽出するプロンプトなら以下
            description="This is the main description.\n- Including a task list style item\n- Another item\n\nThis could be acceptance criteria.",
            tasks=[], relational_definition=[], relational_issues=[], acceptance=[], # 他は空リスト
            labels=None, milestone=None, assignees=None # メタ情報は None
        )
    ]
)


# --- 既存テストケース (変更なし、上記の ai_parser フィクスチャを使用) ---

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
    # description の期待値を修正 (プロンプトによるが、Descriptionセクションのみを期待)
    assert issue1.description == "This issue has everything."
    assert issue1.tasks == ["Task 1", "Task 2"]
    assert issue1.relational_definition == ["REQ-001", "REQ-002"]
    assert issue1.relational_issues == ["#123", "https://github.com/owner/repo/issues/456"]
    assert issue1.acceptance == ["AC 1 passed", "AC 2 checked"]
    assert issue1.labels == ["backend", "feature", "priority:high"]
    assert issue1.milestone == "Sprint 1 Goals"
    assert issue1.assignees == ["developer1", "developer2"]

    # 2つ目のIssueの詳細を確認
    issue2 = result.issues[1]
    assert issue2.title == "Second Issue with Label only"
    assert issue2.description == "Minimal body." # Descriptionセクションのみを期待
    assert issue2.labels == ["frontend"]
    assert issue2.milestone is None
    assert issue2.assignees is None
    assert issue2.tasks == []

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
    # description の期待値を修正 (モデルに合わせる)
    assert issue.description == EXPECTED_PARSED_DATA_NO_META.issues[0].description
    assert issue.labels is None
    assert issue.milestone is None
    assert issue.assignees is None
    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_NO_META})


def test_ai_parser_parse_empty_input(ai_parser: AIParser):
    """空のMarkdownテキストが入力された場合、Chainは呼ばれずに空の結果が返るか"""
    empty_markdown = ""
    expected_empty_result = ParsedRequirementData(issues=[])
    result = ai_parser.parse(empty_markdown)
    assert result == expected_empty_result
    ai_parser.chain.invoke.assert_not_called()


def test_ai_parser_llm_api_authentication_error(ai_parser: AIParser):
    """LLM APIで認証エラーが発生した場合に AiParserError (API Call Failed) が発生するか"""
    mock_api_error = API_AUTH_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    with pytest.raises(AiParserError, match="AI API call failed:") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error


def test_ai_parser_llm_api_timeout_error(ai_parser: AIParser):
    """LLM APIでタイムアウトエラーが発生した場合に AiParserError (Unexpected) が発生するか"""
    # AiParser内のAPIエラーハンドリングによっては、TimeoutErrorがそのまま上がるのではなく、
    # AiParserErrorでラップされることを想定する。
    mock_api_error = API_TIMEOUT_ERROR
    ai_parser.chain.invoke.side_effect = mock_api_error
    # _GOOGLE_ERRORS に TimeoutError が含まれていれば 'AI API call failed:' になるはず
    # そうでなければ 'An unexpected error occurred'
    # ai_parser.py の実装に合わせて期待値を調整
    expected_match = "AI API call failed:" if isinstance(mock_api_error, tuple(getattr(ai_parser, '_GOOGLE_ERRORS', ()) + getattr(ai_parser, '_OPENAI_ERRORS', ()))) else "An unexpected error occurred during AI parsing."
    with pytest.raises(AiParserError, match=expected_match) as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_api_error


def test_ai_parser_output_parsing_error(ai_parser: AIParser):
    """LLMが不正な形式のデータを返し、出力パースに失敗した場合 (OutputParserException)"""
    mock_parsing_error = OutputParserException("Failed to parse LLM output")
    ai_parser.chain.invoke.side_effect = mock_parsing_error
    with pytest.raises(AiParserError, match="Failed to parse AI output.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_parsing_error


def test_ai_parser_unexpected_error(ai_parser: AIParser):
    """その他の予期せぬエラーが発生した場合"""
    mock_unexpected_error = ValueError("Something completely unexpected.")
    ai_parser.chain.invoke.side_effect = mock_unexpected_error
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing.") as excinfo:
        ai_parser.parse("Some markdown text")
    assert excinfo.value.original_exception is mock_unexpected_error


def test_ai_parser_parse_success_different_milestones(ai_parser: AIParser):
    """異なるマイルストーンを持つ複数のIssueを正確にパースできるか"""
    ai_parser.chain.invoke.return_value = EXPECTED_PARSED_DATA_DIFFERENT_MILESTONES
    result = ai_parser.parse(SAMPLE_MARKDOWN_DIFFERENT_MILESTONES)
    assert result == EXPECTED_PARSED_DATA_DIFFERENT_MILESTONES
    assert len(result.issues) == 3

    # Issue 1: マイルストーン「Sprint 1」があることを確認
    issue1 = result.issues[0]
    assert issue1.title == "Issue with Milestone A"
    assert issue1.description == "This issue has milestone A."
    assert issue1.milestone == "Sprint 1"

    # Issue 2: マイルストーン「Sprint 2」があることを確認
    issue2 = result.issues[1]
    assert issue2.title == "Issue with Milestone B"
    assert issue2.description == "This issue has milestone B."
    assert issue2.milestone == "Sprint 2"

    # Issue 3: マイルストーンがないことを確認
    issue3 = result.issues[2]
    assert issue3.title == "Issue with No Milestone"
    assert issue3.description == "This issue has no milestone."
    assert issue3.milestone is None

    ai_parser.chain.invoke.assert_called_once_with(
        {"markdown_text": SAMPLE_MARKDOWN_DIFFERENT_MILESTONES})
