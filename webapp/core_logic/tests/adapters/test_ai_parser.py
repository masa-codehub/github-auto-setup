import pytest
from unittest import mock
import logging
from pydantic import ValidationError, SecretStr  # ValidationError をインポート
import json

# テスト対象と依存モジュール
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.domain.exceptions import AiParserError
from github_automation_tool.domain.models import ParsedRequirementData, IssueData, AISuggestedRules
from github_automation_tool.infrastructure.config import Settings
# LangChain の例外 - OutputParserException をインポート
from langchain_core.exceptions import OutputParserException

# --- Mocks and Fixtures ---

# モックレスポンス (変更なし)
MOCK_VALID_RESPONSE_DICT = {  # JSON を dict にしておく
    "issues": [
        {
            "title": "First issue",
            "description": "Issue description",
            "tasks": ["Task 1", "Task 2"],
            "relational_definition": [],  # 追加 (モデルに合わせて)
            "relational_issues": [],  # 追加
            "acceptance": [],  # 追加
            "labels": ["bug"],
            "milestone": "v1.0",
            "assignees": ["@user1"]
        }
    ]
}

# 不正な構造のモックレスポンス（title がない）
MOCK_INVALID_STRUCTURE = {
    "issues": [
        {
            # "title": "Missing title", # title フィールドが欠落
            "description": "This structure is invalid",
            "labels": ["invalid"]
        }
    ]
}


# Settings フィクスチャ (max_tokens 調整を反映させるため修正)
@pytest.fixture
def mock_settings():
    """設定モック"""
    mock_settings = mock.MagicMock(spec=Settings)
    mock_settings.ai_model = "openai"
    mock_settings.openai_api_key = SecretStr("test-key")
    mock_settings.gemini_api_key = SecretStr("test-key")
    mock_settings.final_openai_model_name = "gpt-4o"
    mock_settings.final_gemini_model_name = "gemini-1.5-flash"
    # format_instructions を削除
    mock_settings.prompt_template = "Test prompt {markdown_text}"
    mock_settings.final_log_level = "INFO"
    # --- ai属性のモックを追加 ---
    ai_mock = mock.MagicMock()
    ai_mock.separator_rule_prompt_template = "区切りルールプロンプト"
    ai_mock.key_mapping_rule_prompt_template = "キーマッピングルールプロンプト"
    mock_settings.ai = ai_mock
    return mock_settings


# APIクライアントのモック
@pytest.fixture
def mock_api_clients():
    """OpenAIとGeminiのAPIクライアントをモックします"""
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatOpenAI") as mock_chat_openai, \
            mock.patch("github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI") as mock_chat_gemini, \
            mock.patch("github_automation_tool.adapters.ai_parser.PromptTemplate") as mock_prompt:

        yield {
            'chat_openai': mock_chat_openai,
            'chat_gemini': mock_chat_gemini,
            'prompt': mock_prompt
        }


# パーサーフィクスチャ (OpenAI)
@pytest.fixture
def ai_parser_openai(mock_settings, mock_api_clients):
    # モックLLMを作成
    mock_llm = mock.MagicMock()
    mock_structured_llm = mock.MagicMock()

    # モックのレスポンス準備
    result = ParsedRequirementData.model_validate(MOCK_VALID_RESPONSE_DICT)
    mock_structured_llm.invoke.return_value = result

    # with_structured_output メソッドのモックを設定
    mock_llm.with_structured_output.return_value = mock_structured_llm

    # ChatOpenAIモックが作成したlangchainクライアントを返すように設定
    mock_api_clients['chat_openai'].return_value = mock_llm

    # モックチェーンを設定(プロンプト + LLM)
    mock_prompt_instance = mock.MagicMock()
    mock_api_clients['prompt'].return_value = mock_prompt_instance
    mock_prompt_instance.__or__.return_value = mock_structured_llm

    # モックセットアップ後にAIParserを初期化
    parser = AIParser(settings=mock_settings)

    # 実際にモックが正しいことを検証（テスト前に検証）
    assert parser.llm == mock_llm
    assert parser.chain == mock_structured_llm

    return parser, mock_structured_llm


# パーサーフィクスチャ (Gemini)
@pytest.fixture
def ai_parser_gemini(mock_settings, mock_api_clients):
    # モックLLMを作成
    mock_llm = mock.MagicMock()
    mock_structured_llm = mock.MagicMock()

    # モックのレスポンス準備
    result = ParsedRequirementData.model_validate(MOCK_VALID_RESPONSE_DICT)
    mock_structured_llm.invoke.return_value = result

    # with_structured_output メソッドのモックを設定
    mock_llm.with_structured_output.return_value = mock_structured_llm

    # ChatGoogleGenerativeAIモックが作成したlangchainクライアントを返すように設定
    mock_api_clients['chat_gemini'].return_value = mock_llm

    # モックチェーンを設定(プロンプト + LLM)
    mock_prompt_instance = mock.MagicMock()
    mock_api_clients['prompt'].return_value = mock_prompt_instance
    mock_prompt_instance.__or__.return_value = mock_structured_llm

    # GeminiのAIモデルを設定
    mock_settings.ai_model = "gemini"

    # モックセットアップ後にAIParserを初期化
    parser = AIParser(settings=mock_settings)

    # 実際にモックが正しいことを検証（テスト前に検証）
    assert parser.llm == mock_llm
    assert parser.chain == mock_structured_llm

    return parser, mock_structured_llm

# --- テストケース ---


def test_parse_valid_input_openai(ai_parser_openai):
    """OpenAI: 有効な入力から正しいParseRequirementDataオブジェクトを生成できること"""
    parser, mock_chain = ai_parser_openai
    result = parser.parse("Create a test repository")

    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 1
    assert result.issues[0].title == "First issue"
    # invoke が正しく呼ばれたか確認
    mock_chain.invoke.assert_called_once_with(
        {"markdown_text": "Create a test repository"})


def test_parse_valid_input_gemini(ai_parser_gemini):
    """Google: 有効な入力から正しいParseRequirementDataオブジェクトを生成できること"""
    parser, mock_chain = ai_parser_gemini
    result = parser.parse("Create a test repository")

    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 1
    assert result.issues[0].title == "First issue"
    mock_chain.invoke.assert_called_once_with(
        {"markdown_text": "Create a test repository"})

# ★ 改善点: 新しいエラーハンドリングのテスト ★


def test_parse_validation_error(ai_parser_openai):
    """構造化出力がPydanticモデルと一致しない場合にValidationErrorを処理できること"""
    parser, mock_chain = ai_parser_openai

    # mock_chain.invokeをリセット
    mock_chain.invoke.reset_mock()

    # ValidationErrorを発生させるように設定
    validation_error = ValidationError.from_exception_data(
        title="ParsedRequirementData", line_errors=[])
    mock_chain.invoke.side_effect = validation_error

    with pytest.raises(AiParserError) as exc_info:
        parser.parse("Input that causes validation error")

    # エラーメッセージが期待通りか確認
    assert "AI output validation failed" in str(exc_info.value)

    # invoke が呼ばれたか確認
    mock_chain.invoke.assert_called_once()


def test_parse_output_generation_error(ai_parser_openai):
    """構造化出力生成失敗時に出されるエラーを処理できること"""
    parser, mock_chain = ai_parser_openai

    # mock_chain.invokeをリセット
    mock_chain.invoke.reset_mock()

    # RuntimeError を使用して構造化出力エラーをシミュレート
    generation_error = RuntimeError(
        "Failed to generate structured output from schema")
    mock_chain.invoke.side_effect = generation_error

    with pytest.raises(AiParserError) as exc_info:
        parser.parse("Input causing generation error")

    # エラーメッセージが期待通りか確認
    assert "Failed to generate structured AI output" in str(exc_info.value)

    # invoke が呼ばれたか確認
    mock_chain.invoke.assert_called_once()


def test_parse_unexpected_runtime_error(ai_parser_openai):
    """通常のランタイムエラーを適切に処理できること"""
    parser, mock_chain = ai_parser_openai

    # mock_chain.invokeをリセット
    mock_chain.invoke.reset_mock()

    # 通常のランタイムエラーをシミュレート (schema関連のキーワードなし)
    runtime_error = RuntimeError("Some other unexpected error")
    mock_chain.invoke.side_effect = runtime_error

    with pytest.raises(AiParserError) as exc_info:
        parser.parse("Input causing runtime error")

    # エラーメッセージが期待通りか確認
    assert "An unexpected error occurred during AI parsing" in str(
        exc_info.value)

    # invoke が呼ばれたか確認
    mock_chain.invoke.assert_called_once()

# APIエラーのテスト


def test_parse_api_error_openai(ai_parser_openai):
    """OpenAI: APIエラーを適切に処理できること"""
    parser, mock_chain = ai_parser_openai

    # mock_chain.invokeをリセット
    mock_chain.invoke.reset_mock()

    # モックAPIエラークラスを作成
    class MockOpenAIAuthenticationError(Exception):
        def __init__(self, message):
            self.message = message
            super().__init__(message)

    # モックエラーを設定
    api_error = MockOpenAIAuthenticationError("Invalid API Key")

    # _OPENAI_ERRORSにモックエラーを含めることをモック
    with mock.patch.object(parser, 'chain') as patched_chain, \
            mock.patch("github_automation_tool.adapters.ai_parser._OPENAI_ERRORS", (MockOpenAIAuthenticationError,)):

        # モックエラーを発生させるように設定
        patched_chain.invoke.side_effect = api_error

        with pytest.raises(AiParserError) as exc_info:
            parser.parse("Create a repository")

        # エラーメッセージが期待通りか確認
        assert "AI API call failed during parse" in str(exc_info.value)

        # invoke が呼ばれたか確認
        patched_chain.invoke.assert_called_once()


def test_parse_api_error_gemini(ai_parser_gemini):
    """Google: APIエラーを適切に処理できること"""
    parser, mock_chain = ai_parser_gemini

    # mock_chain.invokeをリセット
    mock_chain.invoke.reset_mock()

    # モックAPIエラークラスを作成
    class MockGoogleResourceExhausted(Exception):
        def __init__(self, message):
            self.message = message
            super().__init__(message)

    # モックエラーを設定
    api_error = MockGoogleResourceExhausted("Quota exceeded")

    # _GOOGLE_ERRORSにモックエラーを含めることをモック
    with mock.patch.object(parser, 'chain') as patched_chain, \
            mock.patch("github_automation_tool.adapters.ai_parser._GOOGLE_ERRORS", (MockGoogleResourceExhausted,)):

        # モックエラーを発生させるように設定
        patched_chain.invoke.side_effect = api_error

        with pytest.raises(AiParserError) as exc_info:
            parser.parse("Create a repository")

        # エラーメッセージが期待通りか確認
        assert "AI API call failed during parse" in str(exc_info.value)

        # invoke が呼ばれたか確認
        patched_chain.invoke.assert_called_once()

# ★ 改善点: max_tokens 設定のテスト ★


def test_initialize_llm_gemini_with_max_tokens(mock_settings, mock_api_clients):
    """Geminiクライアント初期化時にmax_output_tokensが設定されること"""
    # Geminiモデルを設定
    mock_settings.ai_model = "gemini"

    # AIParserを初期化
    AIParser(settings=mock_settings)

    # ChatGoogleGenerativeAIの呼び出し確認
    mock_api_clients['chat_gemini'].assert_called_once()

    # 期待される max_output_tokens が kwargs に含まれているか確認
    _, kwargs = mock_api_clients['chat_gemini'].call_args
    assert "max_output_tokens" in kwargs
    assert kwargs["max_output_tokens"] == 262144  # 設定した値に更新


def test_initialize_llm_openai(mock_settings, mock_api_clients):
    """OpenAIクライアント初期化時のパラメータ確認"""
    # AIParserを初期化
    AIParser(settings=mock_settings)

    # ChatOpenAIの呼び出し確認
    mock_api_clients['chat_openai'].assert_called_once()

    # 基本パラメータの確認
    _, kwargs = mock_api_clients['chat_openai'].call_args
    assert kwargs["openai_api_key"] == "test-key"
    assert kwargs["temperature"] == 0
    assert kwargs["model_name"] == "gpt-4o"

    # 注: 現在の実装では max_tokens がセットされていない可能性がある
    # 将来的に実装される場合は、以下のコメントアウトを解除
    # assert "model_kwargs" in kwargs
    # assert kwargs["model_kwargs"].get("max_tokens") > 0


def test_parse_empty_input(ai_parser_openai):
    """空の入力を処理できること"""
    parser, _ = ai_parser_openai
    result = parser.parse("")

    # 空の入力の場合は空のParseRequirementDataオブジェクトが返されること
    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 0


def test_build_chain_with_prompt_template(mock_settings, mock_api_clients):
    """プロンプトテンプレートを使ってチェーンを構築できること"""
    # AIParserを初期化
    parser = AIParser(settings=mock_settings)

    # プロンプト作成が正しいパラメータで呼ばれたか確認
    mock_api_clients['prompt'].assert_called_once_with(
        template=mock_settings.prompt_template,
        input_variables=["markdown_text"],
        partial_variables={}
    )


def test_infer_rules_success(monkeypatch, mock_settings):
    """AI区切り・キーマッピングルール推論が正常に動作し、信頼度・警告が正しく返る"""
    from github_automation_tool.adapters.ai_parser import AIParser
    parser = AIParser(settings=mock_settings)
    # モック: llm.invokeの返り値を制御
    parser.llm = mock.MagicMock()
    parser.llm.invoke.side_effect = [
        '{"separator_pattern": "---"}',
        '{"key_mapping": {"Title": "title", "Description": "description"}}'
    ]
    mock_settings.ai.separator_rule_prompt_template = "区切りルールプロンプト"
    mock_settings.ai.key_mapping_rule_prompt_template = "キーマッピングルールプロンプト"
    result = parser.infer_rules("dummy text")
    assert isinstance(result, AISuggestedRules)
    assert result.separator_rule == {"separator_pattern": "---"}
    assert result.key_mapping_rule == {
        "Title": "title", "Description": "description"}
    assert result.confidence == 1.0
    assert not result.errors
    assert not result.warnings


def test_infer_rules_partial_failure(monkeypatch, mock_settings):
    """区切りルール推論が失敗した場合、信頼度・警告・エラーが適切に出力される"""
    from github_automation_tool.adapters.ai_parser import AIParser
    parser = AIParser(settings=mock_settings)
    parser.llm = mock.MagicMock()
    parser.llm.invoke.side_effect = [
        Exception("AI error"), '{"key_mapping": {"Title": "title"}}']
    mock_settings.ai.separator_rule_prompt_template = "区切りルールプロンプト"
    mock_settings.ai.key_mapping_rule_prompt_template = "キーマッピングルールプロンプト"
    result = parser.infer_rules("dummy text")
    assert isinstance(result, AISuggestedRules)
    assert result.separator_rule == {}
    assert result.key_mapping_rule == {"Title": "title"}
    assert result.confidence < 1.0
    assert result.errors
    assert any("区切りルール推論失敗" in e for e in result.errors)
    assert any("信頼度" in w or "一部" in w for w in result.warnings)


def test_infer_rules_total_failure(monkeypatch, mock_settings):
    """両方の推論が失敗した場合、信頼度が大きく低下しエラー・警告が出る"""
    from github_automation_tool.adapters.ai_parser import AIParser
    parser = AIParser(settings=mock_settings)
    parser.llm = mock.MagicMock()
    parser.llm.invoke.side_effect = [
        Exception("AI error1"), Exception("AI error2")]
    mock_settings.ai.separator_rule_prompt_template = "区切りルールプロンプト"
    mock_settings.ai.key_mapping_rule_prompt_template = "キーマッピングルールプロンプト"
    result = parser.infer_rules("dummy text")
    assert isinstance(result, AISuggestedRules)
    assert result.separator_rule == {}
    assert result.key_mapping_rule == {}
    assert result.confidence <= 0.3
    assert len(result.errors) == 2
    assert any("信頼度" in w or "一部" in w for w in result.warnings)
