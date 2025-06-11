from rest_framework import serializers
from core_logic.domain.models import (
    CreateGitHubResourcesResult, 
    CreateIssuesResult, 
    IssueData, 
    ParsedRequirementData
)


class IssueDataSerializer(serializers.Serializer):
    temp_id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    tasks = serializers.ListField(
        child=serializers.CharField(), required=False)
    relational_definition = serializers.ListField(
        child=serializers.CharField(), required=False)
    relational_issues = serializers.ListField(
        child=serializers.CharField(), required=False)
    acceptance = serializers.ListField(
        child=serializers.CharField(), required=False)
    labels = serializers.ListField(
        child=serializers.CharField(), allow_null=True, required=False)
    milestone = serializers.CharField(allow_null=True, required=False)
    assignees = serializers.ListField(
        child=serializers.CharField(), allow_null=True, required=False)


class ParsedRequirementDataSerializer(serializers.Serializer):
    issues = IssueDataSerializer(many=True)


class CreateIssuesResultSerializer(serializers.Serializer):
    created_issue_details = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()), required=False)
    skipped_issue_titles = serializers.ListField(
        child=serializers.CharField(), required=False)
    failed_issue_titles = serializers.ListField(
        child=serializers.CharField(), required=False)
    errors = serializers.ListField(
        child=serializers.CharField(), required=False)
    validation_failed_assignees = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()), required=False)


class CreateGitHubResourcesResultSerializer(serializers.Serializer):
    repository_url = serializers.CharField(allow_null=True, required=False)
    project_node_id = serializers.CharField(allow_null=True, required=False)
    project_name = serializers.CharField(allow_null=True, required=False)
    created_labels = serializers.ListField(
        child=serializers.CharField(), required=False)
    failed_labels = serializers.ListField(child=serializers.ListField(
        child=serializers.CharField()), required=False)
    processed_milestones = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()), required=False)
    failed_milestones = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()), required=False)
    issue_result = CreateIssuesResultSerializer(
        allow_null=True, required=False)
    project_items_added_count = serializers.IntegerField(required=False)
    project_items_failed = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()), required=False)
    fatal_error = serializers.CharField(allow_null=True, required=False)
    dry_run = serializers.BooleanField(required=False)

# 他のドメインモデル用シリアライザもここに追加