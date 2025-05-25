from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from .forms import FileUploadForm


class TopPageViewTest(TestCase):
    """トップページViewのテスト"""

    def test_top_page_status_code(self):
        """トップページが200を返すことを確認"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)

    def test_top_page_uses_correct_template(self):
        """トップページで正しいテンプレートが使われていることを確認"""
        response = self.client.get(reverse('app:top_page'))
        self.assertTemplateUsed(response, 'top_page.html')
        self.assertTemplateUsed(response, 'base.html')

    def test_top_page_contains_main_content(self):
        """トップページ固有の主要な要素・文言が含まれていることを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertContains(
            response, "GitHub Automation Tool へようこそ！", msg_prefix="ウェルカムメッセージのH1タイトルが含まれていません")
        self.assertContains(response, "Bootstrap 5 のスタイルが正しく適用されています。",
                            msg_prefix="Bootstrap適用確認メッセージが含まれていません")
        self.assertContains(response, "btn-primary",
                            msg_prefix="Bootstrapのプライマリボタンクラスが見つかりません")
        self.assertContains(response, "card-title",
                            msg_prefix="カードタイトルのクラスが見つかりません")
        self.assertContains(response, "機能概要",
                            msg_prefix="機能概要セクションが見つかりません")
        self.assertContains(response, "利用開始",
                            msg_prefix="利用開始セクションが見つかりません")

    def test_top_page_inherits_base_elements(self):
        """base.html由来のナビゲーションバー・フッター要素が含まれていることを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertContains(response, "navbar",
                            msg_prefix="ナビゲーションバー要素が見つかりません")
        self.assertContains(response, "footer",
                            msg_prefix="フッター要素が見つかりません")

    def test_action_panel_section_exists(self):
        """アクション実行パネルのUI骨格要素が存在することを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)

        # パネル全体
        self.assertContains(response, 'id="action-panel-section"',
                            msg_prefix="Action panel section not found")
        # 見出しテキスト
        self.assertContains(response, '<h5 class="mb-0">3. Execute Actions</h5>', html=True,
                            msg_prefix="Action panel header text incorrect or missing")

        # GitHub登録エリア
        self.assertContains(response, 'name="repo_name"',
                            msg_prefix="Repository name input not found")
        self.assertContains(response, 'name="project_name"',
                            msg_prefix="Project name input not found")
        self.assertContains(response, 'id="dry-run-checkbox"',
                            msg_prefix="Dry run checkbox not found")
        self.assertContains(response, 'id="github-submit-button"',
                            msg_prefix="GitHub submit button not found")

        # ローカル保存エリア
        self.assertContains(response, 'name="local_path"',
                            msg_prefix="Local path input not found")
        self.assertContains(response, 'id="local-save-button"',
                            msg_prefix="Local save button not found")

    def test_notification_area_exists(self):
        """結果表示用の通知エリアが存在することを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="result-notification-area"',
                            msg_prefix="Result notification area not found")

    def test_upload_section_exists(self):
        """ファイルアップロードエリアのUI骨格要素が存在することを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)

        # セクション全体
        self.assertContains(
            response, 'id="upload-section"',
            msg_prefix="Upload section not found"
        )
        self.assertContains(
            response, 'id="upload-form"',
            msg_prefix="Upload form not found"
        )

        # フォーム属性の厳密な検証
        html = response.content.decode()
        self.assertRegex(
            html,
            r'<form[^>]*method="post"[^>]*>',
            msg="formタグにmethod='post'が設定されていません"
        )
        self.assertRegex(
            html,
            r'<form[^>]*enctype="multipart/form-data"[^>]*>',
            msg="formタグにenctype='multipart/form-data'が設定されていません"
        )
        self.assertRegex(
            html,
            r'<input[^>]*name="csrfmiddlewaretoken"[^>]*>',
            msg="CSRFトークンが含まれていません"
        )
        # ファイル入力フィールドの厳密な検証（長い行をさらに分割）
        self.assertRegex(
            html,
            r'<input[^>]*type="file"[^>]*class="form-control"[^>]*'
            r'id="issue-file-input"[^>]*>',
            msg="ファイル入力フィールドの属性が正しくありません"
        )
        self.assertContains(
            response, '<button class="btn btn-primary" id="upload-button"',
            msg_prefix="Upload button not found"
        )

    def test_upload_section_message_area(self):
        """通知エリアのHTML構造が存在することのみを検証（メッセージ内容やalertクラスは検証しない）"""
        response = self.client.get(reverse('app:top_page'))
        html = response.content.decode()
        self.assertIn('id="result-notification-area"', html)
        # メッセージブロックの構造が空でも存在することを確認
        # メッセージ内容やalertクラスは検証しない

    def test_issue_list_section_exists(self):
        """Issue一覧表示エリアのUI骨格要素が存在することを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)

        # セクション全体
        self.assertContains(response, 'id="issue-list-section"',
                            msg_prefix="Issue list section not found")

        # 主要なUI要素
        self.assertContains(response, 'id="select-all-button"',
                            msg_prefix="Select all button not found")
        self.assertContains(response, 'id="deselect-all-button"',
                            msg_prefix="Deselect all button not found")
        self.assertContains(response, '<table id="issue-table"',
                            msg_prefix="Issue table not found")
        self.assertContains(response, '<th scope="col">Title</th>',
                            msg_prefix="Table header 'Title' not found")
        self.assertContains(response, 'class="form-check-input issue-checkbox"',
                            count=2, msg_prefix="Issue row checkboxes not found or not enough samples")

        # --- 詳細表示UIの検証を追加 ---
        self.assertContains(response, 'data-bs-toggle="collapse" data-bs-target="#issueDetail',
                            count=2, msg_prefix="Collapse toggle for issue details not found or not enough samples")
        self.assertContains(response, 'id="issueDetail1"',
                            msg_prefix="Detail container for first dummy issue not found")
        self.assertContains(response, 'id="issueDetail2"',
                            msg_prefix="Detail container for second dummy issue not found")
        self.assertContains(response, 'class="issue-title-clickable"', count=2,
                            msg_prefix="Clickable title class not found on dummy issues")
        self.assertContains(response, "(Click to expand)",
                            count=2, msg_prefix="Expand hint not found")
        self.assertContains(response, "<strong>Description:</strong>", count=2,
                            msg_prefix="Dummy description placeholder not found in details")

    def test_ai_configuration_section_exists(self):
        """AI設定エリアのUI骨格要素が存在することを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertEqual(response.status_code, 200)

        # AI設定セクションのタイトル
        self.assertContains(response, '<h6 class="card-title mt-4">AI Configuration</h6>',
                            msg_prefix="AI Configuration section title not found")

        # AIプロバイダー選択 (ラジオボタン)
        self.assertContains(response, 'name="ai_provider"',
                            msg_prefix="AI provider select radio buttons not found")
        self.assertContains(response, 'id="ai_provider_openai"',
                            msg_prefix="OpenAI provider radio button not found")
        self.assertContains(response, 'id="ai_provider_gemini"',
                            msg_prefix="Gemini provider radio button not found")

        # OpenAI モデル名選択ドロップダウン
        self.assertContains(response, 'id="openai-model-select"',
                            msg_prefix="OpenAI model select dropdown not found")
        self.assertContains(response, 'name="openai_model_name"',
                            msg_prefix="OpenAI model name attribute missing")
        self.assertContains(response, '<option value="gpt-4o" selected>gpt-4o (Default)</option>',
                            msg_prefix="OpenAI default model option missing")
        self.assertContains(response, '<option value="gpt-4">gpt-4</option>',
                            msg_prefix="OpenAI gpt-4 model option missing")
        self.assertContains(response, '<option value="gpt-3.5-turbo">gpt-3.5-turbo</option>',
                            msg_prefix="OpenAI gpt-3.5-turbo model option missing")

        # Gemini モデル名選択ドロップダウン
        self.assertContains(response, 'id="gemini-model-select"',
                            msg_prefix="Gemini model select dropdown not found")
        self.assertContains(response, 'name="gemini_model_name"',
                            msg_prefix="Gemini model name attribute missing")
        self.assertContains(response, '<option value="gemini-1.5-flash">gemini-1.5-flash</option>',
                            msg_prefix="Gemini default model option missing")
        self.assertContains(response, '<option value="gemini-1.5-flash" selected>gemini-1.5-flash (Default)</option>',
                            msg_prefix="Gemini default model option (selected) missing")
        self.assertContains(response, '<option value="gemini-1.5-pro-latest">gemini-1.5-pro-latest</option>',
                            msg_prefix="Gemini pro-latest model option missing")
        self.assertContains(response, '<option value="gemini-1.0-pro">gemini-1.0-pro</option>',
                            msg_prefix="Gemini 1.0-pro model option missing")

        # APIキー入力 (単一フォーム)
        self.assertContains(response, 'id="api-key-input"',
                            msg_prefix="API key input not found")
        self.assertContains(response, 'name="api_key"',
                            msg_prefix="API key input name attribute missing")


class FileUploadFormTests(TestCase):
    def test_file_required(self):
        form = FileUploadForm(files={})
        self.assertFalse(form.is_valid())
        self.assertIn('issue_file', form.errors)
        self.assertIn('このフィールドは必須です', str(form.errors['issue_file']))

    def test_invalid_extension(self):
        file = SimpleUploadedFile(
            "test.txt", b"dummy content", content_type="text/plain"
        )
        form = FileUploadForm(files={'issue_file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('issue_file', form.errors)
        self.assertIn('Unsupported file extension',
                      str(form.errors['issue_file']))

    def test_valid_extensions(self):
        for ext, ctype in [
            ("md", "text/markdown"),
            ("yml", "application/x-yaml"),
            ("yaml", "application/x-yaml"),
            ("json", "application/json")
        ]:
            file = SimpleUploadedFile(
                f"test.{ext}", b"dummy content", content_type=ctype
            )
            form = FileUploadForm(files={'issue_file': file})
            self.assertTrue(
                form.is_valid(), f"Extension {ext} should be valid"
            )

    def test_file_size_limit_exact(self):
        # 10MBちょうど
        size = 10 * 1024 * 1024
        file = SimpleUploadedFile(
            "test.md", b"a" * size, content_type="text/markdown"
        )
        form = FileUploadForm(files={'issue_file': file})
        self.assertTrue(form.is_valid(), "10MBちょうどは許可されるべき")

    def test_file_size_limit_exceeded(self):
        # 10MB + 1バイト
        size = 10 * 1024 * 1024 + 1
        file = SimpleUploadedFile(
            "test.md", b"a" * size, content_type="text/markdown"
        )
        form = FileUploadForm(files={'issue_file': file})
        self.assertFalse(form.is_valid())
        self.assertIn('issue_file', form.errors)
        self.assertIn('File size cannot exceed',
                      str(form.errors['issue_file']))
