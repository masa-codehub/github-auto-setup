from rest_framework import serializers
from core_logic.domain.models import IssueData, ParsedRequirementData


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
