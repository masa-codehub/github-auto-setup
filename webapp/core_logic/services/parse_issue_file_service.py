"""
ParseIssueFileService: ファイル名・内容からAIパースを行う共通サービス
"""
import os
from core_logic.domain.models import ParsedRequirementData
from core_logic.domain.exceptions import ParsingError, AiParserError
from core_logic.adapters.markdown_issue_parser import MarkdownIssueParser
from core_logic.adapters.yaml_issue_parser import YamlIssueParser
from core_logic.adapters.json_issue_parser import JsonIssueParser
from core_logic.adapters.ai_parser import AIParser
import json
import yaml


class ParseIssueFileService:
    def __init__(self, ai_parser: AIParser):
        self.ai_parser = ai_parser
        self.markdown_parser = MarkdownIssueParser()
        self.yaml_parser = YamlIssueParser()
        self.json_parser = JsonIssueParser()

    def parse(self, file_name: str, file_content_bytes: bytes) -> ParsedRequirementData:
        file_content = file_content_bytes.decode('utf-8')
        ext = os.path.splitext(file_name)[1].lower()
        if ext in ['.md', '.markdown']:
            initial_parser = self.markdown_parser
        elif ext in ['.yml', '.yaml']:
            initial_parser = self.yaml_parser
        elif ext == '.json':
            initial_parser = self.json_parser
        else:
            raise ParsingError(f"Unsupported file extension: {ext}")
        raw_issue_blocks = initial_parser.parse(file_content)
        if not raw_issue_blocks:
            return ParsedRequirementData(issues=[])
        if ext in ['.md', '.markdown']:
            combined_content = '\n---\n'.join(raw_issue_blocks)
            parsed_data: ParsedRequirementData = self.ai_parser.parse(
                combined_content)
        else:
            # YAML/JSONはlist[dict]→文字列化してAIパース
            if ext in ['.yml', '.yaml']:
                content_to_parse = yaml.dump(
                    raw_issue_blocks, default_flow_style=False, sort_keys=False)
            elif ext == '.json':
                content_to_parse = json.dumps(
                    raw_issue_blocks, indent=2, ensure_ascii=False)
            else:
                content_to_parse = str(raw_issue_blocks)
            parsed_data: ParsedRequirementData = self.ai_parser.parse(
                content_to_parse)
        return parsed_data
