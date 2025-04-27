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


# --- LLM 実装 (try-except でインポート) ---
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
    logging.debug("langchain-openai not installed.")
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None
    logging.debug("langchain-google-genai not installed.")

# --- API エラークラス (try-except でインポート) ---
_OPENAI_ERRORS = tuple()
_GOOGLE_ERRORS = tuple()
try:
    from openai import AuthenticationError as OpenAIAuthenticationError
    from openai import RateLimitError as OpenAIRateLimitError
    from openai import APIError as OpenAIAPIError
    from openai import APITimeoutError as OpenAITimeoutError
    from openai import NotFoundError as OpenAINotFoundError # 追加
    _OPENAI_ERRORS = (OpenAIAuthenticationError, OpenAIRateLimitError,
                      OpenAIAPIError, OpenAITimeoutError, OpenAINotFoundError)
except ImportError:
    logging.debug("openai library not fully available for specific error handling.")
try:
    from google.api_core.exceptions import PermissionDenied as GooglePermissionDenied
    from google.api_core.exceptions import ResourceExhausted as GoogleResourceExhausted
    from google.api_core.exceptions import GoogleAPICallError, DeadlineExceeded as GoogleTimeoutError
    from google.api_core.exceptions import NotFound as GoogleNotFound # 追加
    _GOOGLE_ERRORS = (GooglePermissionDenied, GoogleResourceExhausted,
                      GoogleAPICallError, GoogleTimeoutError, GoogleNotFound)
except ImportError:
    logging.debug("google-api-core library not fully available for specific error handling.")


logger = logging.getLogger(__name__)


class AIParser:
    """
    LangChain と Generative AI を使用して Markdown テキストから Issue 情報を解析するクラス。
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # llm と chain の初期化を __init__ から分離し、必要時に行うように変更も検討可能
        # ここでは従来通り __init__ で初期化
        self.llm: BaseChatModel = self._initialize_llm()
        self.chain: RunnableSerializable = self._build_chain() # build_chain は llm を使用する
        logger.info(
            f"AIParser initialized with model type: {self.settings.ai_model}")

    def _initialize_llm(self) -> BaseChatModel:
        """設定に基づいて適切な LangChain LLM クライアントを初期化します。"""
        model_type = self.settings.ai_model.lower() # 環境変数優先のモデルタイプ
        logger.debug(f"Initializing LLM for model type: {model_type}")

        # ---- 修正箇所: settingsから最終的なモデル名を取得 ----
        openai_model_name = self.settings.final_openai_model_name
        gemini_model_name = self.settings.final_gemini_model_name
        # --------------------------------------------

        try:
            if model_type == "openai":
                if ChatOpenAI is None:
                    raise ImportError("langchain-openai is not installed.")
                api_key = self.settings.openai_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("OpenAI API Key is required but missing.") # エラーメッセージ修正

                # ---- 修正箇所: 設定されたモデル名を使用 ----
                logger.info(f"Using OpenAI model: {openai_model_name}")
                llm = ChatOpenAI(
                    openai_api_key=api_key.get_secret_value(),
                    temperature=0,
                    model_name=openai_model_name # 取得したモデル名を使用
                )
                # ----------------------------------
                logger.info(f"ChatOpenAI client initialized with model: {openai_model_name}")
                return llm

            elif model_type == "gemini":
                if ChatGoogleGenerativeAI is None:
                    raise ImportError("langchain-google-genai is not installed.")
                api_key = self.settings.gemini_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("Gemini API Key is required but missing.") # エラーメッセージ修正

                # ---- 修正箇所: 設定されたモデル名を使用 ----
                logger.info(f"Using Gemini model: {gemini_model_name}")
                llm = ChatGoogleGenerativeAI(
                    google_api_key=api_key.get_secret_value(),
                    model=gemini_model_name, # 取得したモデル名を使用
                    temperature=0,
                    convert_system_message_to_human=True
                )
                # ----------------------------------
                logger.info(f"ChatGoogleGenerativeAI client initialized with model: {gemini_model_name}")
                return llm
            else:
                raise ValueError(
                    f"Unsupported AI model type in settings: '{model_type}'. Supported: 'openai', 'gemini'")

        # --- エラーハンドリング (変更なし、ただしログメッセージは改善可能) ---
        except ImportError as e:
            raise AiParserError(f"Import error for '{model_type}': {e}", e) from e
        except ValueError as e: # APIキー不足など
            raise AiParserError(f"Configuration error for '{model_type}': {e}", e) from e
        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
             error_type = type(e).__name__
             model_name_in_error = openai_model_name if model_type == 'openai' else gemini_model_name
             logger.error(f"API Error during LLM initialization ({model_type}, model: {model_name_in_error}): {error_type} - {e}", exc_info=False)
             raise AiParserError(f"AI API Error during initialization ({error_type}): {e}", e) from e
        except Exception as e:
            logger.error(f"Unexpected error initializing LLM client ({model_type}): {e}", exc_info=True)
            raise AiParserError(f"Could not initialize LLM client ({model_type}): {e}", e) from e

    def _build_chain(self) -> RunnableSerializable:
        """プロンプト、LLM、出力パーサーを繋いだ LangChain Chain を構築します。"""
        try:
            output_parser = PydanticOutputParser(pydantic_object=ParsedRequirementData)

            # ---- 修正箇所: プロンプトテンプレートを設定から取得 ----
            if not self.settings.prompt_template or not self.settings.prompt_template.strip():
                 raise ValueError("Prompt template is missing or empty in settings.")
            prompt_template_text = self.settings.prompt_template
            logger.debug(f"Using prompt template loaded from settings (length: {len(prompt_template_text)}).")
            # --------------------------------------------

            prompt = PromptTemplate(
                template=prompt_template_text,
                input_variables=["markdown_text"],
                partial_variables={"format_instructions": output_parser.get_format_instructions()},
            )

            chain = prompt | self.llm | output_parser
            logger.debug("LangChain processing chain built successfully.")
            return chain
        except ValueError as e: # プロンプトテンプレート欠落など
            logger.error(f"Failed to build LangChain chain due to configuration: {e}")
            raise AiParserError(f"Failed to build LangChain chain: {e}") from e
        except Exception as e:
            logger.error(f"Failed to build LangChain chain: {e}", exc_info=True)
            raise AiParserError(f"Failed to build LangChain chain: {e}", original_exception=e) from e

    def parse(self, markdown_text: str) -> ParsedRequirementData:
        """Markdownテキストを解析し、構造化されたIssueデータを抽出します。(修正なし)"""
        # (既存の parse メソッド実装は変更不要)
        logger.info(f"Starting AI parsing for Markdown text (length: {len(markdown_text)})...")
        if not markdown_text or not markdown_text.strip():
            logger.warning("Input markdown text is empty or whitespace only, returning empty data.")
            return ParsedRequirementData(issues=[])
        if not hasattr(self, 'chain') or self.chain is None:
            logger.error("AI processing chain is not initialized.")
            raise AiParserError("AI processing chain is not initialized.")
        try:
            logger.debug("Invoking AI processing chain...")
            result = self.chain.invoke({"markdown_text": markdown_text})
            if not isinstance(result, ParsedRequirementData):
                logger.error(f"AI output parsing resulted in unexpected type: {type(result)}")
                raise AiParserError(f"AI parsing resulted in unexpected data type: {type(result)}")
            logger.info(f"Successfully parsed {len(result.issues)} issue(s).")
            return result
        except OutputParserException as e:
            logger.error(f"Failed to parse AI output structure: {e}", exc_info=True)
            raise AiParserError("Failed to parse AI output.", original_exception=e) from e
        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
            error_type = type(e).__name__
            logger.error(f"AI API call failed during parse: {error_type} - {e}")
            raise AiParserError(f"AI API call failed during parse ({error_type}): {e}", original_exception=e) from e
        except Exception as e:
            logger.exception(f"An unexpected error occurred during AI parsing: {e}")
            raise AiParserError("An unexpected error occurred during AI parsing.", original_exception=e) from e
