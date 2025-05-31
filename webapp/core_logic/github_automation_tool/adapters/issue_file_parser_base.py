from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
import yaml
import json

# RawIssueBlock: 各Issueを表す未加工データ（Markdownならstr、YAML/JSONならdict）
RawIssueBlock = Union[str, Dict[str, Any]]
# IntermediateParsingResult: ファイル全体をパースした結果（Issueブロックのリスト）
IntermediateParsingResult = List[RawIssueBlock]

class AbstractIssueFileParser(ABC):
    @abstractmethod
    def parse(self, file_content: str) -> IntermediateParsingResult:
        """
        ファイル内容文字列を解析し、Issueブロックのリストに分割する。
        Args:
            file_content: ファイルから読み込まれた文字列全体。
        Returns:
            Issueブロックの中間表現のリスト。
        """
        pass

class YamlIssueParser(AbstractIssueFileParser):
    def __init__(self, issues_key="issues"):
        self.issues_key = issues_key
    def parse(self, file_content: str):
        if not file_content or not file_content.strip():
            return []
        try:
            data = yaml.safe_load(file_content)
        except yaml.YAMLError as e:
            raise ValueError("Invalid YAML format") from e
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if self.issues_key in data and isinstance(data[self.issues_key], list):
                return data[self.issues_key]
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []

class JsonIssueParser(AbstractIssueFileParser):
    def __init__(self, issues_key="issues"):
        self.issues_key = issues_key
    def parse(self, file_content: str):
        if not file_content or not file_content.strip():
            return []
        try:
            data = json.loads(file_content)
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON format") from e
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if self.issues_key in data and isinstance(data[self.issues_key], list):
                return data[self.issues_key]
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []
