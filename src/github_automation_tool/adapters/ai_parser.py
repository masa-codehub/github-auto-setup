import logging
from typing import Type
# pydantic.ValidationError をインポート
from pydantic import ValidationError

# 設定、データモデル、カスタム例外をインポート
from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError

# --- LangChain のコアコンポーネント ---
from langchain_core.prompts import PromptTemplate
# PydanticOutputParser は不要になる
# from langchain_core.output_parsers import PydanticOutputParser
# OutputParserExceptionもwith_structured_outputでは使用しないため削除
# from langchain_core.exceptions import OutputParserException
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

# --- API エラークラス (変更なし) ---
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
    with_structured_output を利用して信頼性を向上。
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # llm と chain の初期化を build_chain から分離
        self.llm: BaseChatModel = self._initialize_llm()
        self.chain: RunnableSerializable = self._build_chain()
        logger.info(
            f"AIParser initialized with model type: {self.settings.ai_model}")

    def _initialize_llm(self) -> BaseChatModel:
        """設定に基づいて適切な LangChain LLM クライアントを初期化します。"""
        model_type = self.settings.ai_model.lower()
        logger.debug(f"Initializing LLM for model type: {model_type}")

        openai_model_name = self.settings.final_openai_model_name
        gemini_model_name = self.settings.final_gemini_model_name

        # ★ 改善点: Gemini の max_output_tokens を設定 ★
        # 大量の Issue 抽出に対応するため、出力トークン上限を増やす
        # (モデルの最大コンテキストウィンドウを超えない範囲で設定が必要)
        # gemini-1.5-flash は最大 8192 なので、ここでは 8192 を設定してみる
        # 注意: これは入力トークンとの合計がモデル上限 (1M) を超えない場合に有効
        gemini_max_output_tokens = 262144
        # OpenAI (gpt-4o等) の max_tokens は LangChain 側で直接設定するパラメータが
        # 標準的でない場合がある。多くの場合、モデルのデフォルト出力上限 (例: 4k or 16k) が適用される。
        # 必要であれば model_kwargs={'max_tokens': VALUE} のような形で指定を試みる。
        # ここでは一旦 OpenAI 側は LangChain/Model のデフォルトに任せる。

        try:
            if model_type == "openai":
                if ChatOpenAI is None:
                    raise ImportError("langchain-openai is not installed.")
                api_key = self.settings.openai_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("OpenAI API Key is required but missing.")

                logger.info(f"Using OpenAI model: {openai_model_name}")
                # OpenAI の max_tokens はデフォルトに任せるか、必要なら model_kwargs で指定
                llm = ChatOpenAI(
                    openai_api_key=api_key.get_secret_value(),
                    temperature=0,
                    model_name=openai_model_name
                    model_kwargs={"max_tokens": 262144} # 必要に応じて追加検討
                )
                logger.info(f"ChatOpenAI client initialized with model: {openai_model_name}")
                return llm

            elif model_type == "gemini":
                if ChatGoogleGenerativeAI is None:
                    raise ImportError("langchain-google-genai is not installed.")
                api_key = self.settings.gemini_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("Gemini API Key is required but missing.")

                logger.info(f"Using Gemini model: {gemini_model_name}")
                logger.info(f"Setting max_output_tokens for Gemini: {gemini_max_output_tokens}")
                llm = ChatGoogleGenerativeAI(
                    google_api_key=api_key.get_secret_value(),
                    model=gemini_model_name,
                    temperature=0,
                    convert_system_message_to_human=True,
                    # ★ 改善点: max_output_tokens を指定 ★
                    max_output_tokens=gemini_max_output_tokens
                )
                logger.info(f"ChatGoogleGenerativeAI client initialized with model: {gemini_model_name}")
                return llm
            else:
                raise ValueError(
                    f"Unsupported AI model type in settings: '{model_type}'. Supported: 'openai', 'gemini'")

        except ImportError as e:
            raise AiParserError(f"Import error for '{model_type}': {e}", e) from e
        except ValueError as e:
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
        """
        プロンプトと構造化出力LLMを繋いだ LangChain Chain を構築します。
        PydanticOutputParser は使用しません。
        """
        try:
            # ★ 改善点: PydanticOutputParser を削除 ★
            # output_parser = PydanticOutputParser(pydantic_object=ParsedRequirementData) # 不要

            if not self.settings.prompt_template or not self.settings.prompt_template.strip():
                 raise ValueError("Prompt template is missing or empty in settings.")
            prompt_template_text = self.settings.prompt_template

            # プロンプトテンプレートを調整 (フォーマット指示は不要になる可能性)
            # format_instructions 変数を除去、または空文字にする
            # (with_structured_outputがスキーマを渡すため、明示的なJSON指示は不要/有害な場合がある)
            prompt = PromptTemplate(
                template=prompt_template_text,
                input_variables=["markdown_text"],
                partial_variables={} # format_instructions は削除
            )
            logger.debug(f"Using prompt template loaded from settings (length: {len(prompt_template_text)}). Format instructions removed/ignored.")

            # ★ 改善点: with_structured_output を使用 ★
            # Pydantic モデルを直接指定して構造化出力を指示
            structured_llm = self.llm.with_structured_output(ParsedRequirementData)
            logger.debug("LLM configured with structured output for ParsedRequirementData.")

            chain = prompt | structured_llm
            logger.debug("LangChain processing chain built successfully using with_structured_output.")
            return chain

        except ValueError as e:
            logger.error(f"Failed to build LangChain chain due to configuration: {e}")
            raise AiParserError(f"Failed to build LangChain chain: {e}") from e
        except Exception as e:
            logger.error(f"Failed to build LangChain chain: {e}", exc_info=True)
            raise AiParserError(f"Failed to build LangChain chain: {e}", original_exception=e) from e

    def parse(self, markdown_text: str) -> ParsedRequirementData:
        """Markdownテキストを解析し、構造化されたIssueデータを抽出します。"""
        logger.info(f"Starting AI parsing for Markdown text (length: {len(markdown_text)})...")
        if not markdown_text or not markdown_text.strip():
            logger.warning("Input markdown text is empty or whitespace only, returning empty data.")
            return ParsedRequirementData(issues=[])
        if not hasattr(self, 'chain') or self.chain is None:
            logger.error("AI processing chain is not initialized.")
            raise AiParserError("AI processing chain is not initialized.")
        try:
            logger.debug("Invoking AI processing chain with structured output...")
            # invoke に渡す辞書のキーは PromptTemplate の input_variables と一致させる
            result = self.chain.invoke({"markdown_text": markdown_text})

            if not isinstance(result, ParsedRequirementData):
                # 通常、with_structured_output が成功すれば型は一致するはずだが念のため
                logger.error(f"AI output parsing resulted in unexpected type: {type(result)}")
                raise AiParserError(f"AI parsing resulted in unexpected data type: {type(result)}")

            if not result.issues:
                 logger.warning("AI parsing finished, but no issues were extracted from the provided Markdown.")
            else:
                 logger.info(f"Successfully parsed {len(result.issues)} issue(s).")

            return result

        # ★ 改善点: エラーハンドリング更新 ★
        except ValidationError as e: # Pydantic のバリデーションエラーを直接捕捉
             # with_structured_output が失敗して不正な構造を返した場合に発生しうる
             logger.error(f"AI output validation failed: {e}", exc_info=False)
             raise AiParserError(f"AI output validation failed: {e}", original_exception=e) from e
        # OutputGenerationException は利用できないため、RuntimeError や ValueError など
        # 一般的な例外を使用してエラーハンドリングを実装
        except (RuntimeError, ValueError) as e: # 構造化出力生成時の一般的なエラー
             # 注意: 文字列マッチング（"structured output" in str(e).lower()）は
             # ライブラリの実装変更によりエラーメッセージが変わると脆弱になる可能性があります。
             # 将来的に、より具体的な例外クラスが利用可能になった場合は、そちらへの移行を検討します。
             if "structured output" in str(e).lower() or "schema" in str(e).lower():
                 logger.error(f"AI output generation failed: {e}", exc_info=True)
                 raise AiParserError("Failed to generate structured AI output.", original_exception=e) from e
             else:
                 # その他のランタイムエラーは一般的な例外として処理
                 logger.exception(f"An unexpected error occurred during AI parsing: {e}")
                 raise AiParserError("An unexpected error occurred during AI parsing.", original_exception=e) from e
        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e: # APIエラーはそのまま
            error_type = type(e).__name__
            logger.error(f"AI API call failed during parse: {error_type} - {e}")
            raise AiParserError(f"AI API call failed during parse ({error_type}): {e}", original_exception=e) from e
        except Exception as e: # その他の予期せぬエラー
            logger.exception(f"An unexpected error occurred during AI parsing: {e}")
            raise AiParserError("An unexpected error occurred during AI parsing.", original_exception=e) from e
