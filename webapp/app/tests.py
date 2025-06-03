from django.test import TestCase, Client
from django.urls import reverse

class HealthCheckAPITest(TestCase):
    def test_health_check_api_status_code(self):
        response = self.client.get('/api/healthcheck/')
        self.assertEqual(response.status_code, 200)

    def test_health_check_api_content(self):
        response = self.client.get('/api/healthcheck/')
        self.assertTrue(response.get('Content-Type', '').startswith('application/json'))
        self.assertEqual(response.json(), {"status": "ok", "message": "Django REST Framework is working!"})

    def test_browsable_api_enabled(self):
        response = self.client.get('/api/healthcheck/', HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.get('Content-Type', ''))
        self.assertContains(response, 'Django REST framework')
