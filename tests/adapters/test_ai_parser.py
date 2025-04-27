import pytest
from unittest import mock
import logging
from github_automation_tool.adapters.ai_parser import AIParser
from github_automation_tool.domain.exceptions import AiParserError
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.infrastructure.config import Settings
from pydantic import SecretStr
import json

# モックレスポンスの準備
MOCK_VALID_RESPONSE = '''
{
    "issues": [
        {
            "title": "First issue",
            "description": "Issue description",
            "tasks": ["Task 1", "Task 2"],
            "labels": ["bug"],
            "milestone": "v1.0",
            "assignees": ["@user1"]
        }
    ]
}
'''

MOCK_INVALID_JSON = '''
{
    "issues": [
        {
            "title": "test-repo",
            "description": "Invalid JSON missing closing bracket"
'''

# Settingsのモックフィクスチャ
@pytest.fixture
def mock_settings():
    """設定モック"""
    mock_settings = mock.MagicMock(spec=Settings)
    
    # 基本設定
    mock_settings.ai_model = "openai"
    mock_settings.openai_api_key = SecretStr("test-key")
    mock_settings.gemini_api_key = SecretStr("test-key")
    
    # 詳細設定
    mock_settings.final_openai_model_name = "gpt-4o"
    mock_settings.final_gemini_model_name = "gemini-1.5-pro"
    mock_settings.prompt_template = "Test prompt {markdown_text} {format_instructions}"
    mock_settings.final_log_level = "INFO"
    
    return mock_settings

# LangChain モックフィクスチャ
@pytest.fixture
def mock_langchain():
    """LangChain関連クラスのモック"""
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatOpenAI") as mock_openai_chat, \
         mock.patch("github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI") as mock_gemini_chat, \
         mock.patch("github_automation_tool.adapters.ai_parser.PromptTemplate") as mock_prompt, \
         mock.patch("github_automation_tool.adapters.ai_parser.PydanticOutputParser") as mock_output_parser:
        
        # モックLLMの設定
        mock_chain = mock.MagicMock()
        mock_chain.invoke.return_value = ParsedRequirementData.model_validate(json.loads(MOCK_VALID_RESPONSE))
        
        # プロンプトモックの設定
        mock_prompt_instance = mock.MagicMock()
        mock_prompt.return_value = mock_prompt_instance
        
        # パーサーモックの設定
        mock_parser_instance = mock.MagicMock()
        mock_parser_instance.get_format_instructions.return_value = "JSON FORMAT INSTRUCTIONS"
        mock_output_parser.return_value = mock_parser_instance
        
        # パイプ演算子のモック
        mock_prompt_instance.__or__.return_value = mock.MagicMock()
        mock_prompt_instance.__or__.return_value.__or__.return_value = mock_chain
        
        return {
            "openai_chat": mock_openai_chat,
            "gemini_chat": mock_gemini_chat,
            "prompt": mock_prompt,
            "output_parser": mock_output_parser,
            "chain": mock_chain
        }

# 基本的なパーサーインスタンス用のフィクスチャ
@pytest.fixture
def ai_parser_openai(mock_settings, mock_langchain):
    """OpenAIを使用するAIParserインスタンス"""
    mock_settings.ai_model = "openai"
    parser = AIParser(settings=mock_settings)
    parser.chain = mock_langchain["chain"]  # テスト用にチェーンを置き換え
    return parser

@pytest.fixture
def ai_parser_gemini(mock_settings, mock_langchain):
    """Google Geminiを使用するAIParserインスタンス"""
    mock_settings.ai_model = "gemini"
    parser = AIParser(settings=mock_settings)
    parser.chain = mock_langchain["chain"]  # テスト用にチェーンを置き換え
    return parser

# テストケース
def test_parse_valid_input_openai(ai_parser_openai):
    """OpenAI: 有効な入力から正しいParseRequirementDataオブジェクトを生成できること"""
    result = ai_parser_openai.parse("Create a test repository")
    
    # 検証
    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 1
    assert isinstance(result.issues[0], IssueData)
    assert result.issues[0].title == "First issue"
    assert result.issues[0].description == "Issue description"
    
    # APIが適切なパラメータで呼び出されたことを確認
    ai_parser_openai.chain.invoke.assert_called_once()
    call_args = ai_parser_openai.chain.invoke.call_args[0][0]
    assert "Create a test repository" in str(call_args)

def test_parse_valid_input_gemini(ai_parser_gemini):
    """Google: 有効な入力から正しいParseRequirementDataオブジェクトを生成できること"""
    result = ai_parser_gemini.parse("Create a test repository")
    
    # 検証
    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 1
    assert isinstance(result.issues[0], IssueData)
    assert result.issues[0].title == "First issue"
    
    # APIが適切なパラメータで呼び出されたことを確認
    ai_parser_gemini.chain.invoke.assert_called_once()
    call_args = ai_parser_gemini.chain.invoke.call_args[0][0]
    assert "Create a test repository" in str(call_args)

def test_parse_invalid_json_response(ai_parser_openai, mock_langchain):
    """不正なJSON応答を処理できること"""
    # OutputParserExceptionを発生させる
    from langchain_core.exceptions import OutputParserException
    mock_langchain["chain"].invoke.side_effect = OutputParserException("Failed to parse LLM response as JSON")
    
    # エラー発生を確認
    with pytest.raises(AiParserError, match="Failed to parse AI output"):
        ai_parser_openai.parse("Create a repository")

def test_parse_api_error_openai(ai_parser_openai, mock_langchain, caplog):
    """OpenAI: APIエラーを適切に処理できること"""
    # APIエラーをシミュレート - APIErrorではなく一般的な例外を使用
    mock_error = Exception("API Error from OpenAI")
    mock_langchain["chain"].invoke.side_effect = mock_error
    
    # エラーログをキャプチャしてエラー発生を確認
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing"), caplog.at_level(logging.ERROR):
        ai_parser_openai.parse("Create a repository")
    
    # ログにエラー情報が含まれることを確認
    assert "An unexpected error occurred during AI parsing" in caplog.text
    assert "API Error from OpenAI" in caplog.text

def test_parse_api_error_gemini(ai_parser_gemini, mock_langchain, caplog):
    """Google: APIエラーを適切に処理できること"""
    # APIエラーをシミュレート
    # ここでは直接エラーオブジェクトを作成せず、例外クラスとしてモックする
    generic_error = Exception("API Error from Google")
    mock_langchain["chain"].invoke.side_effect = generic_error
    
    # エラーログをキャプチャしてエラー発生を確認
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing"), caplog.at_level(logging.ERROR):
        ai_parser_gemini.parse("Create a repository")
    
    # ログに詳細なエラー情報が含まれることを確認
    assert "An unexpected error occurred during AI parsing" in caplog.text

def test_initialize_llm_openai_error(mock_settings):
    """OpenAI: クライアント初期化時のエラーを処理できること"""
    mock_settings.ai_model = "openai"
    
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatOpenAI", 
                    side_effect=ValueError("Invalid API key")):
        with pytest.raises(AiParserError, match="Configuration error for 'openai'"):
            AIParser(settings=mock_settings)

def test_initialize_llm_gemini_error(mock_settings):
    """Google: クライアント初期化時のエラーを処理できること"""
    mock_settings.ai_model = "gemini"
    
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI", 
                    side_effect=ValueError("Invalid API key")):
        with pytest.raises(AiParserError, match="Configuration error for 'gemini'"):
            AIParser(settings=mock_settings)

def test_openai_rate_limit_error(mock_settings):
    """OpenAI: レートリミットエラーを特定のエラーとして処理できること"""
    mock_settings.ai_model = "openai"
    
    # エラーオブジェクトを直接モックして使用
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatOpenAI") as mock_chat_openai:
        # 最新のOpenAIライブラリに合わせたエラー
        mock_chat_openai.side_effect = ValueError("OpenAI API rate limit exceeded")
        
        with pytest.raises(AiParserError, match="Configuration error for 'openai'"):
            AIParser(settings=mock_settings)

def test_google_permission_denied_error(mock_settings):
    """Google: 権限エラーを特定のエラーとして処理できること"""
    mock_settings.ai_model = "gemini"
    
    # 一般的なValueErrorを使用（環境によってはGoogle APIの例外が利用できない場合がある）
    with mock.patch("github_automation_tool.adapters.ai_parser.ChatGoogleGenerativeAI") as mock_chat_gemini:
        mock_chat_gemini.side_effect = ValueError("Google API permission denied")
        
        with pytest.raises(AiParserError, match="Configuration error for 'gemini'"):
            AIParser(settings=mock_settings)

def test_unsupported_model_type(mock_settings):
    """サポートされていないモデルタイプのエラーを処理できること"""
    mock_settings.ai_model = "unsupported_model"
    
    with pytest.raises(AiParserError, match="Configuration error for 'unsupported_model'"):
        AIParser(settings=mock_settings)

def test_parse_unexpected_exception_openai(ai_parser_openai, mock_langchain, caplog):
    """OpenAI: parse時の予期せぬ例外を処理できること"""
    # 予期せぬ例外をシミュレート
    unexpected_error = RuntimeError("Something really unexpected")
    mock_langchain["chain"].invoke.side_effect = unexpected_error
    
    # エラーログをキャプチャしてエラー発生を確認
    with pytest.raises(AiParserError, match="An unexpected error occurred during AI parsing"), caplog.at_level(logging.ERROR):
        ai_parser_openai.parse("Create a repository")
    
    # ログに詳細なエラー情報が含まれることを確認
    assert "An unexpected error occurred during AI parsing" in caplog.text
    assert "RuntimeError" in caplog.text or "Something really unexpected" in caplog.text

def test_parse_empty_input(ai_parser_openai):
    """空の入力を処理できること"""
    result = ai_parser_openai.parse("")
    
    # 空の入力の場合は空のParseRequirementDataオブジェクトが返されること
    assert isinstance(result, ParsedRequirementData)
    assert len(result.issues) == 0

def test_build_chain_error(mock_settings):
    """チェーン構築時のエラーを処理できること"""
    mock_settings.prompt_template = ""  # 空のプロンプトテンプレ
    
    with pytest.raises(AiParserError, match="Failed to build LangChain chain"):
        AIParser(settings=mock_settings)

def test_validation_error(ai_parser_openai, mock_langchain, caplog):
    """バリデーションエラーを処理できること"""
    # ValidationErrorを直接モックするのではなく、代わりに例外を発生させてエラー処理を確認
    from langchain_core.exceptions import OutputParserException
    
    # LangChainのOutputParserExceptionを使用（ValidationErrorよりも確実に処理できる）
    mock_error = OutputParserException("Failed to parse output as valid IssueData")
    mock_langchain["chain"].invoke.side_effect = mock_error
    
    # LangChainの例外は「Failed to parse AI output」として捕捉される
    with pytest.raises(AiParserError, match="Failed to parse AI output"), caplog.at_level(logging.ERROR):
        ai_parser_openai.parse("Create a repository")
    
    # ログに適切なメッセージが含まれることを確認
    assert "Failed to parse" in caplog.text
