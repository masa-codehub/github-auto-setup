"""
RuleBasedMapperService: 推論ルールに基づくIssueDataマッピングサービス
"""
from typing import Any, Dict, List, Optional
from github_automation_tool.domain.models import IssueData
import logging

logger = logging.getLogger(__name__)

# --- 値変換ロジック（純粋関数） ---


def to_list_by_comma(text: str) -> List[str]:
    return [item.strip() for item in text.split(',') if item.strip()]


def to_list_by_newline(text: str) -> List[str]:
    return [item.strip() for item in text.splitlines() if item.strip()]


def extract_mentions(text: str) -> List[str]:
    import re
    return re.findall(r'@([\w\-]+)', text)

# --- メインサービス ---


class RuleBasedMapperService:
    """
    キーマッピングルール・Issueブロック・デフォルトルールに基づきIssueDataへ変換
    """

    def __init__(self, default_mapping: Optional[Dict[str, Any]] = None):
        self.default_mapping = default_mapping or {}

    def map_block_to_issue_data(self, block: Dict[str, Any], key_mapping_rule: Dict[str, Any]) -> IssueData:
        field_map = key_mapping_rule.copy()
        # デフォルトルールの適用（AI推論が不十分な場合のフォールバック）
        for k, v in self.default_mapping.items():
            field_map.setdefault(k, v)

        data = {}
        warnings = []
        # フィールドごとに値抽出・変換
        for field in IssueData.model_fields.keys():
            input_key = field_map.get(field)
            if not input_key:
                continue
            raw_value = block.get(input_key)
            if raw_value is None:
                continue
            # 変換ルール適用
            convert_rule = field_map.get(f"{field}__convert")
            try:
                if convert_rule == "to_list_by_comma":
                    data[field] = to_list_by_comma(raw_value)
                elif convert_rule == "to_list_by_newline":
                    data[field] = to_list_by_newline(raw_value)
                elif convert_rule == "extract_mentions":
                    data[field] = extract_mentions(raw_value)
                else:
                    data[field] = raw_value
            except Exception as e:
                warnings.append(f"変換失敗: {field} ({convert_rule}): {e}")
        # title必須チェック
        if not data.get("title") or not str(data["title"]).strip():
            raise ValueError("titleフィールドが空、またはマッピングできません")
        # 警告ログ
        for f in IssueData.model_fields.keys():
            if f not in data:
                warnings.append(f"マッピング失敗: {f}")
        if warnings:
            logger.warning("RuleBasedMapperService: %s", "; ".join(warnings))
        return IssueData(**data)
