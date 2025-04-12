# src/github_automation_tool/__init__.py
import importlib.metadata
try:
    __version__ = importlib.metadata.version("github-automation-tool")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.1.0"  # フォールバック
