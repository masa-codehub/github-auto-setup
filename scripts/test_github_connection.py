# scripts/test_github_connection.py

import typer
import logging
import sys
from typing_extensions import Annotated
from pathlib import Path
from githubkit import GitHub

# TODO: Consider making the project installable (pip install -e .)
# or using PYTHONPATH environment variable for more robust module resolution.
# This sys.path manipulation is for convenience in this specific test script.
# Add webapp/core_logic to path if needed
# sys.path.insert(0, str(Path(__file__).parent.parent / 'webapp' / 'core_logic'))

try:
    from github_automation_tool.infrastructure.config import load_settings, Settings
    from github_automation_tool.adapters import GitHubAppClient
    from github_automation_tool.domain.exceptions import (
        GitHubAuthenticationError, GitHubRateLimitError, GitHubClientError
    )
    from githubkit.exception import RequestFailed
except ImportError as e:
    print(
        f"ERROR: Failed to import necessary project modules: {e}", file=sys.stderr)
    print("Please ensure the script is run from the correct directory or adjust sys.path.", file=sys.stderr)
    print(f"Current sys.path: {sys.path}", file=sys.stderr)
    sys.exit(1)

# Basic Logging Setup (Adjust level via LOG_LEVEL env var if needed)
# Note: config.py now defines log_level, so this basicConfig level might be overridden
# if the main application logging is configured differently. For this script, INFO is likely sufficient.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Test connection and authentication to the GitHub API using the configured PAT.")


@app.command()
def main():
    """
    Loads settings, initializes GitHubAppClient, checks authentication, and verifies PAT scopes.
    """
    logger.info("--- Starting GitHub Connection Test ---")
    all_checks_passed = True
    settings: Settings | None = None

    # --- 1. Load Settings ---
    try:
        settings = load_settings()
        logger.info("Configuration loaded.")
        if not settings.github_pat or not settings.github_pat.get_secret_value():
            logger.error("GitHub PAT is required but not set in settings.")
            print("ERROR: GitHub PAT is missing. Please set GITHUB_PAT.",
                  file=sys.stderr)
            raise typer.Exit(code=1)
        logger.info("GitHub PAT: Set (Value hidden)")

    except Exception as e:
        logger.error(f"Failed to load settings: {e}", exc_info=True)
        print(f"\nERROR: Failed to load settings. Ensure .env file exists or GITHUB_PAT environment variable is set.", file=sys.stderr)
        raise typer.Exit(code=1)

    # --- 2. Initialize GitHub Client ---
    github_client: GitHubAppClient | None = None
    try:
        logger.info("Initializing GitHubAppClient...")
        github_instance = GitHub(settings.github_pat.get_secret_value())
        github_client = GitHubAppClient(github_instance)
        logger.info("GitHubAppClient initialized successfully.")
    except GitHubAuthenticationError as e:
        logger.error(f"Authentication error during client initialization: {e}")
        print(
            f"\nERROR: Authentication failed during client init. Check PAT validity: {e}", file=sys.stderr)
        all_checks_passed = False
    except GitHubClientError as e:
        logger.error(f"Client error during initialization: {e}", exc_info=True)
        print(
            f"\nERROR: Failed to initialize GitHub client: {e}", file=sys.stderr)
        all_checks_passed = False
    except Exception as e:
        logger.error(
            f"Unexpected error during client initialization: {e}", exc_info=True)
        print(f"\nERROR: Unexpected error during client initialization.",
              file=sys.stderr)
        all_checks_passed = False

    # --- 3. Check Authenticated User ---
    if github_client:
        try:
            logger.info("Attempting to get authenticated user info...")
            # Directly access the githubkit client instance 'gh' from GitHubAppClient
            user_response = github_client.gh.rest.users.get_authenticated()

            if user_response and user_response.parsed_data and hasattr(user_response.parsed_data, 'login'):
                username = user_response.parsed_data.login
                logger.info(
                    f"Successfully retrieved authenticated user: {username}")
                print(f"Authenticated User: {username}")
            else:
                logger.error(
                    "Could not retrieve authenticated user login name from response.")
                print(
                    "ERROR: Failed to parse authenticated user response.", file=sys.stderr)
                all_checks_passed = False

        except GitHubAuthenticationError as e:
            logger.error(f"Authentication failed when getting user info: {e}")
            print(
                f"\nERROR: Authentication failed when getting user info. Check PAT validity and permissions: {e}", file=sys.stderr)
            all_checks_passed = False
        except GitHubClientError as e:
            logger.error(
                f"Client error when getting user info: {e}", exc_info=True)
            print(
                f"\nERROR: API client error when getting user info: {e}", file=sys.stderr)
            all_checks_passed = False
        except Exception as e:
            logger.error(
                f"Unexpected error getting user info: {e}", exc_info=True)
            print(f"\nERROR: Unexpected error getting user info.", file=sys.stderr)
            all_checks_passed = False

    # --- 4. Check Rate Limit and Scopes ---
    if github_client:
        try:
            logger.info(
                "Attempting to get rate limit info (includes scopes)...")
            rate_limit_response = github_client.gh.rest.rate_limit.get()

            if rate_limit_response and rate_limit_response.headers:
                scopes = rate_limit_response.headers.get(
                    "X-OAuth-Scopes", "N/A")
                limit = rate_limit_response.headers.get(
                    "X-RateLimit-Limit", "N/A")
                remaining = rate_limit_response.headers.get(
                    "X-RateLimit-Remaining", "N/A")
                reset_time = rate_limit_response.headers.get(
                    "X-RateLimit-Reset", "N/A")

                logger.info(
                    f"Rate Limit Info: Limit={limit}, Remaining={remaining}, Reset={reset_time}")
                logger.info(f"PAT Scopes: {scopes}")
                print(f"PAT Scopes: {scopes}")
                print(f"Rate Limit: {remaining}/{limit}")

                # Validate required scopes (adjust as needed)
                required_scopes = ["repo", "project"]
                scopes_list = [s.strip()
                               for s in scopes.split(',') if s.strip()]
                missing_scopes = [
                    rs for rs in required_scopes if rs not in scopes_list]

                if missing_scopes:
                    logger.error(
                        f"Missing required PAT scopes: {missing_scopes}")
                    print(
                        f"ERROR: PAT is missing required scope(s): {missing_scopes}. Required: {required_scopes}", file=sys.stderr)
                    all_checks_passed = False
                    raise typer.Exit(code=1)  # 明示的にエラー終了
                else:
                    logger.info("Required scopes (repo, project) are present.")

            else:
                logger.error(
                    "Could not retrieve rate limit information or headers from response.")
                print(
                    "ERROR: Failed to parse rate limit response headers.", file=sys.stderr)
                all_checks_passed = False

        except GitHubClientError as e:  # Catch errors during rate limit check
            logger.error(
                f"Client error when getting rate limit info: {e}", exc_info=True)
            print(
                f"\nERROR: API client error when getting rate limit info: {e}", file=sys.stderr)
            all_checks_passed = False
        except Exception as e:
            logger.error(
                f"Unexpected error getting rate limit info: {e}", exc_info=True)
            print(f"\nERROR: Unexpected error getting rate limit info.",
                  file=sys.stderr)
            all_checks_passed = False

    # --- 5. Final Result ---
    logger.info("--- GitHub Connection Test Finished ---")
    if all_checks_passed:
        print("\nSUCCESS: GitHub API connection and PAT scope test passed.")
        raise typer.Exit(code=0)
    else:
        print("\nFAILURE: One or more GitHub connection checks failed. Please review logs and error messages.", file=sys.stderr)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
