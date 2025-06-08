from typing import List, Dict, Any, Union, Optional
import re
import yaml
import json
import logging

logger = logging.getLogger(__name__)

# 型エイリアス
RawIssueBlock = Union[str, Dict[str, Any]]
IntermediateParsingResult = List[RawIssueBlock]


class RuleBasedSplitterSvc:
    """
    推論/フォールバックされた区切りルールとファイル内容に基づき、
    Issueブロックのリスト(IntermediateParsingResult)に分割するサービス。
    Markdown, YAML, JSON 各形式・各区切りルールに対応。
    """

    def split(self, file_content: str, filetype: str, rule: Optional[Dict[str, Any]] = None) -> IntermediateParsingResult:
        if not file_content or not file_content.strip():
            return []
        filetype = filetype.lower()
        if filetype in ("md", "markdown"):
            return self._split_markdown(file_content, rule)
        elif filetype in ("yml", "yaml"):
            return self._split_yaml(file_content)
        elif filetype == "json":
            return self._split_json(file_content)
        else:
            raise ValueError(f"Unsupported filetype: {filetype}")

    def _split_markdown(self, content: str, rule: Optional[Dict[str, Any]]) -> IntermediateParsingResult:
        # ルール例: {"type": "delimiter", "pattern": r"^---$"} など
        if rule is None or rule.get("type") == "delimiter":
            pattern = rule.get("pattern") if rule else r"^---$"
            blocks = [b.strip() for b in re.split(
                pattern, content, flags=re.MULTILINE)]
            return [b for b in blocks if b]
        elif rule.get("type") == "leading_key":
            key = rule.get("key", "Title:")
            # 先頭キーで分割
            blocks = re.split(
                rf"(?=^\s*{re.escape(key)})", content, flags=re.MULTILINE)
            return [b.strip() for b in blocks if b.strip()]
        elif rule.get("type") == "header_level":
            level = rule.get("level", 2)
            pattern = rf"(?=^{'#'*level} )"
            blocks = re.split(pattern, content, flags=re.MULTILINE)
            return [b.strip() for b in blocks if b.strip()]
        else:
            raise ValueError(f"Unknown markdown split rule: {rule}")

    def _split_yaml(self, content: str) -> IntermediateParsingResult:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.warning(
                f"Failed to parse YAML content due to YAMLError: {e}")
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []

    def _split_json(self, content: str) -> IntermediateParsingResult:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []
