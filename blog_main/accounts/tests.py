from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import LoginRecord


class AuthFlowTests(TestCase):

    def test_home_shows_sign_in_links_when_logged_out(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, reverse('login'))
        self.assertContains(response, reverse('signup'))

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse('signup'), {
            'username': 'reader',
            'first_name': 'Asha',
            'last_name': 'Rao',
            'email': 'asha@example.com',
            'password1': 'Str0ng-pass-123',
            'password2': 'Str0ng-pass-123',
        })
        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(username='reader')
        self.assertEqual(user.first_name, 'Asha')
        self.assertEqual(user.email, 'asha@example.com')
        self.assertEqual(LoginRecord.objects.filter(user=user).count(), 1)
        self.assertContains(self.client.get(reverse('home')), 'Hi, reader')

    def test_login_and_logout(self):
        User.objects.create_user('reader', password='Str0ng-pass-123')
        response = self.client.post(reverse('login'), {
            'username': 'reader',
            'password': 'Str0ng-pass-123',
        })
        self.assertRedirects(response, reverse('home'))
        self.assertContains(self.client.get(reverse('home')), 'Sign out')
        record = LoginRecord.objects.get(user__username='reader')
        self.assertEqual(record.ip_address, '127.0.0.1')

        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotContains(self.client.get(reverse('home')), 'Sign out')

    def test_wrong_password_shows_error(self):
        User.objects.create_user('reader', password='Str0ng-pass-123')
        response = self.client.post(reverse('login'), {
            'username': 'reader',
            'password': 'wrong',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user('first', email='asha@example.com', password='x')
        response = self.client.post(reverse('signup'), {
            'username': 'second',
            'first_name': 'Asha',
            'email': 'ASHA@example.com',
            'password1': 'Str0ng-pass-123',
            'password2': 'Str0ng-pass-123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='second').exists())

    def test_wrong_password_is_not_recorded(self):
        User.objects.create_user('reader', password='Str0ng-pass-123')
        self.client.post(reverse('login'), {'username': 'reader', 'password': 'wrong'})
        self.assertFalse(LoginRecord.objects.exists())
