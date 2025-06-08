import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LabelMilestoneNormalizerSvc:
    """
    IssueDataのlabels/milestoneを、正規定義（エイリアス含む）に基づき正規化するサービス。
    """

    def __init__(self, label_defs: List[Dict[str, Any]], milestone_defs: List[Dict[str, Any]]):
        self.label_map = self._build_map(label_defs, key='name')
        self.milestone_map = self._build_map(milestone_defs, key='name')

    def _build_map(self, defs: List[Dict[str, Any]], key: str) -> Dict[str, str]:
        mapping = {}
        for d in defs:
            name = d.get(key)
            aliases = d.get('aliases', [])
            all_keys = [name] + aliases if name else aliases
            for k in all_keys:
                if k:
                    mapping[k.strip().lower()] = name
        return mapping

    def normalize_labels(self, labels: Optional[List[str]]) -> List[str]:
        if not labels:
            return []
        normalized = []
        for label in labels:
            key = label.strip().lower()
            norm = self.label_map.get(key)
            if norm:
                if norm not in normalized:
                    normalized.append(norm)
            else:
                logger.warning(f"[LabelMilestoneNormalizer] 未定義ラベル: '{label}'")
        return normalized

    def normalize_milestone(self, milestone: Optional[str]) -> Optional[str]:
        if not milestone or not milestone.strip():
            return None
        key = milestone.strip().lower()
        norm = self.milestone_map.get(key)
        if norm:
            return norm
        logger.warning(f"[LabelMilestoneNormalizer] 未定義マイルストーン: '{milestone}'")
        return milestone

    def normalize_issue(self, issue_data: Any) -> None:
        # issue_data: IssueData互換オブジェクト
        issue_data.labels = self.normalize_labels(issue_data.labels)
        issue_data.milestone = self.normalize_milestone(issue_data.milestone)
