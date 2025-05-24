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

    def test_top_page_contains_expected_content(self):
        """トップページのHTMLに主要な要素・文言が含まれていることを検証"""
        response = self.client.get(reverse('app:top_page'))
        self.assertContains(
            response, "GitHub Automation Tool トップページ", msg_prefix="トップページのH1タイトルが含まれていません")
        self.assertContains(response, "Bootstrap 5 のスタイルが正しく適用されています。",
                            msg_prefix="Bootstrap適用確認メッセージが含まれていません")
        self.assertContains(response, "navbar",
                            msg_prefix="ベーステンプレートのナビゲーションバー要素が見つかりません")
        self.assertContains(response, "footer",
                            msg_prefix="ベーステンプレートのフッター要素が見つかりません")
