import logging
from typing import Type

# 設定、データモデル、カスタム例外をインポート
from github_automation_tool.infrastructure.config import Settings
from github_automation_tool.domain.models import ParsedRequirementData, IssueData
from github_automation_tool.domain.exceptions import AiParserError

# --- LangChain のコアコンポーネント ---
from langchain_core.prompts import PromptTemplate
# ★ これは output_parsers のまま
from langchain_core.output_parsers import PydanticOutputParser
# ★★★ ここが exceptions になっていますか？ ★★★
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
    # APITimeoutError は NameError 回避のためインポートしない (TimeoutErrorで捕捉)
    from openai import APIError as OpenAIAPIError
    _OPENAI_ERRORS = (OpenAIAuthenticationError,
                      OpenAIRateLimitError, OpenAIAPIError)
except ImportError:
    logging.debug(
        "openai library not fully available for specific error handling.")
try:
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
    タイトル、本文詳細、ラベル、マイルストーン、担当者を抽出します。
    """

    def __init__(self, settings: Settings):
        """
        AIParser を初期化し、設定に基づいてLLMクライアントとChainを構築します。
        """
        self.settings = settings
        self.llm: BaseChatModel = self._initialize_llm()
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
                    raise ImportError("langchain-openai not installed.")
                api_key = self.settings.openai_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("OpenAI API Key missing.")
                llm = ChatOpenAI(openai_api_key=api_key.get_secret_value(
                ), temperature=0, model_name="gpt-3.5-turbo")  # モデル名は設定で可変にすると良い
                logger.info("ChatOpenAI client initialized.")
                return llm
            elif model_type == "gemini":
                if ChatGoogleGenerativeAI is None:
                    raise ImportError("langchain-google-genai not installed.")
                api_key = self.settings.gemini_api_key
                if not api_key or not api_key.get_secret_value():
                    raise ValueError("Gemini API Key missing.")
                llm = ChatGoogleGenerativeAI(google_api_key=api_key.get_secret_value(
                ), model="gemini-pro", temperature=0, convert_system_message_to_human=True)
                logger.info("ChatGoogleGenerativeAI client initialized.")
                return llm
            else:
                raise ValueError(
                    f"Unsupported AI model type: '{self.settings.ai_model}'. Supported: 'openai', 'gemini'")
        except ImportError as e:
            raise AiParserError(
                f"Required library not installed for '{model_type}': {e}", e) from e
        except ValueError as e:
            raise AiParserError(
                f"Configuration error for '{model_type}': {e}", e) from e
        except Exception as e:
            logger.error(
                f"Failed to initialize LLM client for model '{model_type}': {e}", exc_info=True)
            if _OPENAI_ERRORS and isinstance(e, _OPENAI_ERRORS):
                raise AiParserError(f"OpenAI init failed: {e}", e) from e
            elif _GOOGLE_ERRORS and isinstance(e, _GOOGLE_ERRORS):
                raise AiParserError(f"Google AI init failed: {e}", e) from e
            else:
                raise AiParserError(
                    f"Could not initialize LLM client ({model_type}): {e}", e) from e

    def _build_chain(self) -> RunnableSerializable:
        """プロンプト、LLM、出力パーサーを繋いだ LangChain Chain を構築します。"""
        try:
            # ★ 出力パーサーは更新された ParsedRequirementData モデルを使用
            output_parser = PydanticOutputParser(
                pydantic_object=ParsedRequirementData)

            # ★ プロンプトテンプレートを拡張 ★
            prompt_template_text = """
以下のMarkdownテキストから、GitHub Issueとして登録すべき情報を抽出し、指定されたJSON形式で出力してください。
テキストは '---' で区切られた複数のIssue候補で構成されている場合があります。
各Issue候補 ('---' で区切られたブロック) から、以下の情報を正確に抽出してください。

入力テキスト:
```{markdown_text}```

抽出指示:
各Issue候補ごとに、以下のキーを持つJSONオブジェクトを作成してください。
- `title` (string, 必須): Issueのタイトル。通常 `**Title:**` の後に記述されています。
- `description` (string, 必須): Issueの説明文。通常 `**Description:**` の後に記述されています。もし Description セクションがない場合は、Issueの本文から主要な説明部分を抜き出してください。なければ空文字列。
- `tasks` (array of strings, 必須): タスクリスト。通常 `**Tasks:**` や `**タスク:**` の下のリスト項目 (`-` や `- [ ]`)。各タスクを文字列要素とするリスト。なければ空リスト `[]`。
- `relational_definition` (array of strings, 必須): 関連要件のリスト。通常 `**関連要件:**` の下のリスト項目。なければ空リスト `[]`。
- `relational_issues` (array of strings, 必須): 関連Issueのリスト。通常 `**関連Issue:**` の下のリスト項目。なければ空リスト `[]`。
- `acceptance` (array of strings, 必須): 受け入れ基準のリスト。通常 `**受け入れ基準:**` の下のリスト項目。なければ空リスト `[]`。
- `labels` (array of strings | null): ラベルのリスト。通常 `Labels:` の後にカンマ区切りで記述されています。ラベル名をトリムして文字列のリストにしてください。該当セクションがなければ `null`。
- `milestone` (string | null): マイルストーン名。通常 `Milestone:` の後に記述されています。該当セクションがなければ `null`。
- `assignees` (array of strings | null): 担当者のGitHubユーザー名リスト。通常 `Assignee:` の後に `@` 付きでカンマ区切りで記述されています。`@` を除いたユーザー名のみを文字列のリストにしてください。該当セクションがなければ `null`。

抽出した全てのIssueオブジェクトを `issues` というキーを持つJSON配列にまとめてください。

{format_instructions}

注意:
- 各フィールドが存在しない場合は、指示に従い空文字列、空リスト `[]`、または `null` を適切に設定してください。
- Markdownの書式（太字やリスト）は、抽出後の本文関連フィールド（description, tasksなど）では維持せず、プレーンテキストまたはリストの要素として抽出してください。（※この指示はモデルや要件により調整）
- タイトル行やラベル行などのキーワード行自体は、最終的な本文フィールド（descriptionなど）に含めないでください。
"""
            prompt = PromptTemplate(
                template=prompt_template_text,
                input_variables=["markdown_text"],
                partial_variables={
                    "format_instructions": output_parser.get_format_instructions()},
            )

            # LCEL Chain
            chain = prompt | self.llm | output_parser
            logger.debug(
                "LangChain processing chain built successfully (with extended extraction).")
            return chain
        except Exception as e:
            logger.error(
                f"Failed to build LangChain chain: {e}", exc_info=True)
            raise AiParserError(
                f"Failed to build LangChain chain: {e}", original_exception=e) from e

    def parse(self, markdown_text: str) -> ParsedRequirementData:
        """
        Markdownテキストを解析し、構造化されたIssueデータを抽出します。
        (エラーハンドリングロジックは変更なし)
        """
        logger.info(
            f"Starting AI parsing (extended) for Markdown text (length: {len(markdown_text)})...")
        if not markdown_text or not markdown_text.strip():
            logger.warning(
                "Input markdown text is empty or whitespace only, returning empty data.")
            return ParsedRequirementData(issues=[])

        if not hasattr(self, 'chain') or self.chain is None:
            logger.error("AI processing chain is not initialized.")
            raise AiParserError("AI processing chain is not initialized.")

        try:
            logger.debug("Invoking AI processing chain...")
            result = self.chain.invoke({"markdown_text": markdown_text})

            if not isinstance(result, ParsedRequirementData):
                logger.error(
                    f"AI output parsing resulted in unexpected type: {type(result)}")
                raise AiParserError(
                    f"AI parsing resulted in unexpected data type: {type(result)}")

            logger.info(
                f"Successfully parsed {len(result.issues)} issue(s) with extended data.")
            for i, issue in enumerate(result.issues):
                # デバッグログで抽出内容を確認（必要に応じて）
                logger.debug(
                    f"Issue {i+1}: title='{issue.title}', labels={issue.labels}, milestone='{issue.milestone}', assignees={issue.assignees}")
            return result

        except OutputParserException as e:
            logger.error(
                f"Failed to parse AI output structure: {e}", exc_info=True)
            raise AiParserError("Failed to parse AI output.",
                                original_exception=e) from e
        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
            logger.error(f"AI API call failed: {type(e).__name__} - {e}")
            raise AiParserError(
                f"AI API call failed: {e}", original_exception=e) from e
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred during AI parsing: {e}")
            raise AiParserError(
                "An unexpected error occurred during AI parsing.", original_exception=e) from e
