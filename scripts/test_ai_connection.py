# scripts/test_ai_connection.py

import typer
import logging
import sys
from typing_extensions import Annotated
from pathlib import Path

# TODO: Consider making the project installable (pip install -e .)
# or using PYTHONPATH environment variable for more robust module resolution.
# This sys.path manipulation is for convenience in this specific test script.
sys.path.insert(0, str(Path(__file__).parent.parent / 'src')) # Add src to path if needed

try:
    from github_automation_tool.infrastructure.config import load_settings, Settings
    # Import necessary components from ai_parser for client initialization and error handling
    from github_automation_tool.adapters.ai_parser import _OPENAI_ERRORS, _GOOGLE_ERRORS
    # LangChain Models (Try-except for robustness)
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
except ImportError as e:
    print(f"ERROR: Failed to import necessary project modules: {e}", file=sys.stderr)
    print("Please ensure the script is run from the correct directory or adjust sys.path.", file=sys.stderr)
    print(f"Current sys.path: {sys.path}", file=sys.stderr)
    sys.exit(1)

# Basic Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer(help="Test connection to the configured Generative AI model (OpenAI or Gemini).")

@app.command()
def main(
    ai_model_override: Annotated[str, typer.Option("--ai-model", help="Override the AI model from settings ('openai' or 'gemini').")] = None,
):
    """
    Loads settings, initializes the specified AI client, and performs a minimal API call.
    """
    logger.info("--- Starting AI Connection Test ---")

    # --- 1. Load Settings ---
    try:
        settings = load_settings()
        # Determine the model to test - Rely on config default if override is not provided
        model_to_test = (ai_model_override or settings.ai_model).lower()
        # Removed redundant 'else openai' as config.py has a default

        logger.info(f"Configuration loaded. Testing AI Model: {model_to_test}")

        # --- Validate API Key based on selected model ---
        if model_to_test == 'openai':
            if not settings.openai_api_key or not settings.openai_api_key.get_secret_value():
                logger.error("OpenAI API Key is required but not set in settings.")
                print("ERROR: OpenAI API Key is missing. Please set OPENAI_API_KEY.", file=sys.stderr)
                raise typer.Exit(code=1)
            logger.info(f"OpenAI API Key: Set")
        elif model_to_test == 'gemini':
            if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
                logger.error("Gemini API Key is required but not set in settings.")
                print("ERROR: Gemini API Key is missing. Please set GEMINI_API_KEY.", file=sys.stderr)
                raise typer.Exit(code=1)
            logger.info(f"Gemini API Key: Set")
        else:
             # This case should ideally not be reached if config validation is robust
             logger.warning(f"Unknown AI model selected: {model_to_test}. Proceeding, but client initialization might fail.")


    except Exception as e:
        logger.error(f"Failed to load settings or validate API key: {e}", exc_info=True)
        print(f"ERROR: Failed to load settings or validate API key. Ensure .env file exists or environment variables are set correctly.", file=sys.stderr)
        raise typer.Exit(code=1)

    # --- 2. Initialize AI Client ---
    llm_client = None
    try:
        if model_to_test == "openai":
            if ChatOpenAI is None:
                raise ImportError("langchain-openai is not installed. Run 'pip install langchain-openai'")
            # API key presence already checked above
            api_key_secret = settings.openai_api_key
            # Use model name from settings or fallback
            model_name = settings.openai_model_name or "gpt-4o" # Fallback model updated
            logger.info(f"Using OpenAI model: {model_name}")
            llm_client = ChatOpenAI(
                openai_api_key=api_key_secret.get_secret_value(),
                model_name=model_name,
                temperature=0
            )
            logger.info(f"ChatOpenAI client initialized with model: {model_name}")

        elif model_to_test == "gemini":
            if ChatGoogleGenerativeAI is None:
                raise ImportError("langchain-google-genai is not installed. Run 'pip install langchain-google-genai'")
            # API key presence already checked above
            api_key_secret = settings.gemini_api_key
             # Use model name from settings or fallback
            model_name = settings.gemini_model_name or "gemini-2.0-flash" # Fallback model updated
            logger.info(f"Using Gemini model: {model_name}")
            llm_client = ChatGoogleGenerativeAI(
                google_api_key=api_key_secret.get_secret_value(),
                model=model_name,
                temperature=0,
                convert_system_message_to_human=True
            )
            logger.info(f"ChatGoogleGenerativeAI client initialized with model: {model_name}")

        else:
            raise ValueError(f"Unsupported AI model specified: '{model_to_test}'. Use 'openai' or 'gemini'.")

    except (ImportError, ValueError) as e:
        logger.error(f"Failed to initialize AI client: {e}")
        print(f"ERROR: Failed to initialize AI client: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
        logger.error(f"API Error during client initialization: {type(e).__name__} - {e}")
        print(f"ERROR: API Error during client initialization: {type(e).__name__}", file=sys.stderr)
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"Unexpected error during client initialization: {e}", exc_info=True)
        print(f"ERROR: Unexpected error during client initialization.", file=sys.stderr)
        raise typer.Exit(code=1)

    # --- 3. Perform Minimal API Call ---
    if llm_client:
        test_prompt = "Hello!"
        logger.info(f"Attempting minimal API call with prompt: '{test_prompt}'")
        try:
            # Use invoke for a simple call
            response = llm_client.invoke(test_prompt)

            # Check response structure (varies between models, aim for non-error)
            if response and hasattr(response, 'content'):
                 # Check if content is not empty and not an obvious error message
                 response_content = response.content
                 if response_content and isinstance(response_content, str) and 'error' not in response_content.lower():
                     logger.info(f"API call successful. Received response snippet: '{response_content[:50]}...'")
                     print(f"SUCCESS: API connection test for '{model_to_test}' passed.")
                     print(f"Response snippet: {response_content[:100]}{'...' if len(response_content) > 100 else ''}")
                 else:
                     logger.error(f"API call seemed successful but response content might indicate an issue: {response_content}")
                     print(f"WARNING: API call completed for '{model_to_test}' but response content is suspicious. Please check logs.", file=sys.stderr)
                     raise typer.Exit(code=1) # Treat suspicious content as failure for the test
            else:
                 logger.error(f"API call completed but response format was unexpected: {response}")
                 print(f"ERROR: API call completed for '{model_to_test}' but response format was unexpected.", file=sys.stderr)
                 raise typer.Exit(code=1)

        except (*_OPENAI_ERRORS, *_GOOGLE_ERRORS) as e:
            logger.error(f"API Error during test call: {type(e).__name__} - {e}", exc_info=False) # Log less verbosely for common API errors
            print(f"ERROR: API call failed for '{model_to_test}'. Error: {type(e).__name__}", file=sys.stderr)
            print(f"Check your API key, permissions, and network connection.", file=sys.stderr)
            raise typer.Exit(code=1)
        except Exception as e:
            logger.error(f"Unexpected error during API call: {e}", exc_info=True)
            print(f"ERROR: Unexpected error during API call for '{model_to_test}'.", file=sys.stderr)
            raise typer.Exit(code=1)
    else:
        # This case should ideally not be reached if initialization check is robust
        logger.error("LLM client was not initialized.")
        print("ERROR: LLM client failed to initialize.", file=sys.stderr)
        raise typer.Exit(code=1)

    logger.info("--- AI Connection Test Finished ---")

if __name__ == "__main__":
    app()
