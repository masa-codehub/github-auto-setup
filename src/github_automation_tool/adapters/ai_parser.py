import logging
from typing import Type

# 設定、データモデル、カスタム例外をインポート
from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError

# --- LangChain のコアコンポーネント ---
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableSerializable
from langchain_core.language_models.chat_models import BaseChatModel

# --- LLM 実装 (try-except でインポートし、利用可能か確認) ---
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # インポート失敗時は None に設定
    logging.debug("langchain-openai not installed.")
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None  # インポート失敗時は None に設定
    logging.debug("langchain-google-genai not installed.")

# --- API エラークラス (try-except でインポート) ---
# これらを捕捉して AiParserError にラップする
_OPENAI_ERRORS = ()
_GOOGLE_ERRORS = ()
try:
    # OpenAI の主要なエラー
    from openai import AuthenticationError as OpenAIAuthenticationError
    from openai import RateLimitError as OpenAIRateLimitError
    from openai import APITimeoutError as OpenAITimeoutError
    from openai import APIError as OpenAIAPIError
    _OPENAI_ERRORS = (OpenAIAuthenticationError,
                      OpenAIRateLimitError, OpenAITimeoutError, OpenAIAPIError)
except ImportError:
    logging.debug(
        "openai library not fully available for specific error handling.")
try:
    # Google の主要なエラー
    from google.api_core.exceptions import PermissionDenied as GooglePermissionDenied
    from google.api_core.exceptions import ResourceExhausted as GoogleResourceExhausted
    from google.api_core.exceptions import GoogleAPICallError, DeadlineExceeded as GoogleTimeoutError
    _GOOGLE_ERRORS = (GooglePermissionDenied, GoogleResourceExhausted,
                      GoogleAPICallError, GoogleTimeoutError)
except ImportError:
    logging.debug(
        "google-api-core library not fully available for specific error handling.")


logger = logging.getLogger(__name__)


class AIParser:
    """
    LangChain と Generative AI を使用して Markdown テキストから Issue 情報を解析するクラス。
    """

    def __init__(self, settings: Settings):
        """
        AIParser を初期化し、設定に基づいてLLMクライアントとChainを構築します。

        Args:
            settings: APIキーやモデル名を含む設定オブジェクト。

        Raises:
            ValueError: 設定されたAIモデルが無効または対応するライブラリがない場合。
            AiParserError: LLMクライアントの初期化に失敗した場合。
        """
        self.settings = settings
        # LLMクライアントを初期化
        self.llm: BaseChatModel = self._initialize_llm()
        # LangChain Chain を構築
        self.chain: RunnableSerializable = self._build_chain()
        logger.info(
            f"AIParser initialized with model type: {self.settings.ai_model}")

    def _initialize_llm(self) -> BaseChatModel:
        """設定に基づいて適切な LangChain LLM クライアントを初期化します。"""
        model_type = self.settings.ai_model.lower()
        logger.debug(f"Initializing LLM for model type: {model_type}")

        try:
            if model_type == "openai":
                if ChatOpenAI is None:
                    raise ImportError(
                        "langchain-openai is not installed. Cannot use OpenAI model.")
                api_key = self.settings.openai_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("OpenAI API Key is missing in settings.")
                # temperature=0 で出力の再現性を高める。モデル名は環境変数等で可変にすると良い
                llm = ChatOpenAI(openai_api_key=api_key.get_secret_value(
                ), temperature=0, model_name="gpt-3.5-turbo")
                logger.info("ChatOpenAI client initialized.")
                return llm
            elif model_type == "gemini":
                if ChatGoogleGenerativeAI is None:
                    raise ImportError(
                        "langchain-google-genai is not installed. Cannot use Gemini model.")
                api_key = self.settings.gemini_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("Gemini API Key is missing in settings.")
                llm = ChatGoogleGenerativeAI(google_api_key=api_key.get_secret_value(
                ), model="gemini-pro", temperature=0, convert_system_message_to_human=True)
                logger.info("ChatGoogleGenerativeAI client initialized.")
                return llm
            else:
                supported_models = ["openai", "gemini"]
                raise ValueError(
                    f"Unsupported AI model type in settings: '{self.settings.ai_model}'. Supported types: {supported_models}")
        except ImportError as e:
            logger.error(f"Failed to import required LLM library: {e}")
            raise AiParserError(
                f"Required library not installed for model '{model_type}': {e}", original_exception=e) from e
        except ValueError as e:
            logger.error(f"Configuration error for model '{model_type}': {e}")
            raise AiParserError(
                f"Configuration error for model '{model_type}': {e}", original_exception=e) from e
        except Exception as e:
            # APIキー不正などの認証エラーを含む可能性
            logger.error(
                f"Failed to initialize LLM client for model '{model_type}': {e}", exc_info=True)
            # エラータイプに基づいてカスタム例外を出し分ける (テストで捕捉可能にするため)
            if _OPENAI_ERRORS and isinstance(e, _OPENAI_ERRORS):
                raise AiParserError(
                    f"OpenAI API client initialization failed: {e}", original_exception=e) from e
            elif _GOOGLE_ERRORS and isinstance(e, _GOOGLE_ERRORS):
                raise AiParserError(
                    f"Google AI client initialization failed: {e}", original_exception=e) from e
            else:
                raise AiParserError(
                    f"Could not initialize LLM client ({model_type}): {e}", original_exception=e) from e

    def _build_chain(self) -> RunnableSerializable:
        """プロンプト、LLM、出力パーサーを繋いだ LangChain Chain を構築します。"""
        try:
            # 出力形式を定義するPydanticモデルでパーサーを初期化
            output_parser = PydanticOutputParser(
                pydantic_object=ParsedRequirementData)

            # プロンプトテンプレート定義
            prompt_template_text = """
以下のMarkdownテキストは、GitHub Issueとして登録したい内容を含んでいます。
テキストは '---' で区切られた複数のIssue候補で構成されている場合があります。
各Issue候補 ('---' で区切られたブロック) から、タイトル (例: '**Title:** ...') と 本文 (タイトル行と区切り線を除いた残りの全て) を抽出してください。
本文は元のMarkdown形式を維持してください。

入力テキスト:
```{markdown_text}```

抽出指示:
- 各Issue候補ごとに title と body を持つJSONオブジェクトを作成してください。
- 全てのIssueオブジェクトを 'issues' というキーを持つJSON配列にまとめてください。
- 本文が存在しない場合は空文字列 "" としてください。
- 区切り線 '---' 自体は出力に含めないでください。

{format_instructions}
"""
            prompt = PromptTemplate(
                template=prompt_template_text,
                input_variables=["markdown_text"],
                partial_variables={
                    "format_instructions": output_parser.get_format_instructions()},
            )

            # LCEL を使用して Chain を構築
            chain = prompt | self.llm | output_parser
            logger.debug("LangChain processing chain built successfully.")
            return chain
        except Exception as e:
            # Chain構築時のエラーは致命的
            logger.error(
                f"Failed to build LangChain chain: {e}", exc_info=True)
            raise AiParserError(
                f"Failed to build LangChain chain: {e}", original_exception=e) from e

    def parse(self, markdown_text: str) -> ParsedRequirementData:
        """
        Markdownテキストを解析し、構造化されたIssueデータを抽出します。

        Args:
            markdown_text: 解析対象のMarkdown文字列。

        Returns:
            解析結果を含む ParsedRequirementData オブジェクト。

        Raises:
            AiParserError: AI API呼び出しまたは出力のパースに失敗した場合。
        """
        logger.info(
            f"Starting AI parsing for Markdown text (length: {len(markdown_text)})...")
        # 入力が空文字列や空白のみの場合は早期リターン
        if not markdown_text or not markdown_text.strip():
            logger.warning(
                "Input markdown text is empty or whitespace only, returning empty data.")
            return ParsedRequirementData(issues=[])

        # Chainが初期化されているか確認 (念のため)
        if not hasattr(self, 'chain') or self.chain is None:
            logger.error("AI processing chain is not initialized.")
            raise AiParserError("AI processing chain is not initialized.")

        try:
            # Chain を実行して結果を取得
            logger.debug("Invoking AI processing chain...")
            result = self.chain.invoke({"markdown_text": markdown_text})

            # 結果の型をチェック (PydanticOutputParserが成功すれば通常はOK)
            if not isinstance(result, ParsedRequirementData):
                logger.error(
                    f"AI output parsing resulted in unexpected type: {type(result)}")
                # このエラーは OutputParserException で捕捉される可能性が高い
                raise AiParserError(
                    f"AI parsing resulted in unexpected data type: {type(result)}")

            logger.info(
                f"Successfully parsed {len(result.issues)} issue(s) from Markdown.")
            logger.debug(
                f"Parsed result preview: Issues count={len(result.issues)}")
            return result

        # --- エラーハンドリング (テストケースに合わせる) ---
        except OutputParserException as e:
            # LLM出力のパース失敗
            logger.error(
                f"Failed to parse AI output structure: {e}", exc_info=True)
            # test_ai_parser_output_parsing_error の match に合わせる
            raise AiParserError("Failed to parse AI output.",
                                original_exception=e) from e
        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
            # APIキー不正、レート制限などのAPI固有エラー
            logger.error(f"AI API call failed: {type(e).__name__} - {e}")
            # test_ai_parser_llm_api_authentication_error の match に合わせる
            raise AiParserError(
                f"AI API call failed: {e}", original_exception=e) from e
        except Exception as e:
            # タイムアウトエラーやその他の予期せぬエラー
            logger.exception(
                f"An unexpected error occurred during AI parsing: {e}")
            # test_ai_parser_llm_api_timeout_error, test_ai_parser_unexpected_error の match に合わせる
            raise AiParserError(
                "An unexpected error occurred during AI parsing.", original_exception=e) from e
