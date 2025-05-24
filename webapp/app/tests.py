from django.test import TestCase
from django.urls import reverse


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
        self.assertContains(response, 'id="action-form"',
                            msg_prefix="Action form not found")

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
