from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import FileUploadForm
import logging
import os

# core_logicの必要なモジュールを直接import
from core_logic.github_automation_tool.adapters.markdown_issue_parser import MarkdownIssueParser
from core_logic.github_automation_tool.adapters.yaml_issue_parser import YamlIssueParser
from core_logic.github_automation_tool.adapters.json_issue_parser import JsonIssueParser
from core_logic.github_automation_tool.adapters.ai_parser import AIParser
from core_logic.github_automation_tool.infrastructure.config import load_settings
from core_logic.github_automation_tool.domain.models import IssueData, ParsedRequirementData
from core_logic.github_automation_tool.domain.exceptions import AiParserError, ParsingError
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from githubkit import GitHub
from core_logic.github_automation_tool.adapters.github_rest_client import GitHubRestClient
from core_logic.github_automation_tool.adapters.github_graphql_client import GitHubGraphQLClient
from core_logic.github_automation_tool.adapters.assignee_validator import AssigneeValidator
from core_logic.github_automation_tool.use_cases.create_repository import CreateRepositoryUseCase
from core_logic.github_automation_tool.use_cases.create_issues import CreateIssuesUseCase
from core_logic.github_automation_tool.use_cases.create_github_resources import CreateGitHubResourcesUseCase

logger = logging.getLogger(__name__)


def get_parsed_issues_for_session(request):
    """
    セッションに格納されたファイル名・内容を取得し、
    拡張子ごとにパーサーを呼び出し、AIパーサーでParsedRequirementDataを得てissue_listを返す。
    例外時は空リストを返す。
    """
    file_name = request.session.get('uploaded_file_name')
    file_content = request.session.get('uploaded_file_content')
    if not file_name or not file_content:
        return []
    ext = os.path.splitext(file_name)[1].lower()
    try:
        # 1. 拡張子で初期パーサーを選択
        if ext in ['.md', '.markdown']:
            initial_parser = MarkdownIssueParser()
        elif ext in ['.yml', '.yaml']:
            initial_parser = YamlIssueParser()
        elif ext == '.json':
            initial_parser = JsonIssueParser()
        else:
            messages.error(request, f"Unsupported file extension: {ext}")
            return []
        raw_issue_blocks = initial_parser.parse(file_content)
        if not raw_issue_blocks:
            messages.warning(request, "ファイルからIssueブロックが抽出できませんでした。")
            return []
        # 2. AIパーサーで構造化データに変換
        settings = load_settings()
        ai_parser = AIParser(settings=settings)
        # Markdownの場合は結合、YAML/JSONはリストをそのまま
        if ext in ['.md', '.markdown']:
            combined_content = '\n---\n'.join(raw_issue_blocks)
            parsed_data: ParsedRequirementData = ai_parser.parse(combined_content)
        else:
            # YAML/JSONはAIパーサーがリストも受け付ける前提。もし違えばここで変換。
            import yaml
            combined_content = yaml.dump(raw_issue_blocks, allow_unicode=True)
            parsed_data: ParsedRequirementData = ai_parser.parse(combined_content)
        return parsed_data.issues
    except (ParsingError, AiParserError) as e:
        logger.error(f"Issueファイル解析エラー: {e}", exc_info=True)
        messages.error(request, f"ファイル解析中にエラーが発生しました: {e}")
        return []
    except Exception as e:
        logger.exception(f"予期せぬエラー: {e}")
        messages.error(request, f"予期せぬエラーが発生しました: {e}")
        return []


def top_page(request):
    uploaded_file_content = None
    uploaded_file_name = None

    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        try:
            # --- GitHub連携アクション ---
            if 'github_submit' in request.POST:
                settings = load_settings()
                repo_name = request.POST.get('repo_name', '').strip()
                project_name = request.POST.get('project_name', '').strip() or None
                dry_run = request.POST.get('dry_run') == 'on'
                parsed_issue_data = request.session.get('parsed_issue_data')
                if not parsed_issue_data:
                    messages.error(request, "Issueデータが見つかりません。ファイルをアップロードしパースしてください。")
                    return render(request, "top_page.html", {'upload_form': form})
                try:
                    # --- 依存性注入: main.pyのCLI起動時と同等のロジック ---
                    github_instance = GitHub(settings.github_pat.get_secret_value())
                    rest_client = GitHubRestClient(github_instance=github_instance)
                    graphql_client = GitHubGraphQLClient(github_instance=github_instance)
                    assignee_validator = AssigneeValidator(rest_client=rest_client)
                    create_repo_uc = CreateRepositoryUseCase(github_client=rest_client)
                    create_issues_uc = CreateIssuesUseCase(rest_client=rest_client, assignee_validator=assignee_validator)
                    usecase = CreateGitHubResourcesUseCase(
                        rest_client=rest_client,
                        graphql_client=graphql_client,
                        create_repo_uc=create_repo_uc,
                        create_issues_uc=create_issues_uc
                    )
                    usecase.execute(
                        parsed_data=parsed_issue_data,
                        repo_name_input=repo_name,
                        project_name=project_name,
                        dry_run=dry_run
                    )
                    messages.success(request, "GitHub連携アクションが正常に完了しました。")
                except Exception as e:
                    if "rest_client must be an instance" in str(e):
                        messages.error(request, "GitHub認証に失敗しました（テスト用ダミー）。PATまたは設定を確認してください。")
                    else:
                        messages.error(request, f"GitHub連携アクション中に予期せぬエラー: {e}")
                    logger.exception(f"GitHub action error: {e}")
                return render(request, "top_page.html", {'upload_form': form})
            # --- 既存のファイルアップロード処理 ---
            if form.is_valid():
                uploaded_file = form.cleaned_data['issue_file']
                try:
                    uploaded_file_content_bytes = uploaded_file.read()
                    try:
                        uploaded_file_content = uploaded_file_content_bytes.decode('utf-8')
                        logger.info(
                            f"File '{uploaded_file.name}' (type: {uploaded_file.content_type}, size: {uploaded_file.size} bytes) uploaded and read successfully."
                        )
                        messages.success(
                            request, f"File '{uploaded_file.name}' uploaded successfully. Content ready for parsing.")
                        request.session['uploaded_file_content'] = uploaded_file_content
                        request.session['uploaded_file_name'] = uploaded_file.name
                        return redirect('app:top_page')
                    except UnicodeDecodeError:
                        logger.error(f"Failed to decode file '{uploaded_file.name}' as UTF-8.")
                        messages.error(request, f"Failed to decode file '{uploaded_file.name}'. Please ensure it is UTF-8 encoded.")
                except Exception as e:
                    logger.exception(f"Error reading uploaded file '{uploaded_file.name}': {e}")
                    messages.error(request, f"An error occurred while reading the file: {e}")
            else:
                logger.warning(f"File upload form validation failed: {form.errors.as_json()}")
                messages.error(request, "File upload failed. Please check the errors below.")
        except ValueError as e:
            if "GITHUB_PAT cannot be empty" in str(e):
                messages.error(request, "設定エラー: GitHub PATが空です。設定を確認してください。")
            else:
                messages.error(request, f"設定エラー: {e}")
            logger.error(f"設定エラー: {e}", exc_info=True)
        except Exception as e:
            messages.error(request, f"予期せぬエラーが発生しました: {e}")
            logger.exception(f"予期せぬエラー: {e}")
    else:
        form = FileUploadForm()
        if 'uploaded_file_name' in request.session:
            uploaded_file_name = request.session.pop('uploaded_file_name')
            uploaded_file_content = request.session.pop('uploaded_file_content', None)

    context = {
        'upload_form': form,
    }
    issue_list = get_parsed_issues_for_session(request)
    issue_count = len(issue_list)
    context['issue_list'] = issue_list
    context['issue_count'] = issue_count
    return render(request, "top_page.html", context)


@api_view(['GET'])
def health_check_api_view(request):
    """
    シンプルなヘルスチェックAPI。
    DRFが正しくセットアップされているかを確認するために使用。
    """
    return Response({"status": "ok", "message": "Django REST Framework is working!"}, status=status.HTTP_200_OK)