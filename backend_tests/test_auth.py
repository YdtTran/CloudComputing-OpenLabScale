import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import auth_router
from backend.identity import IdentityStore


class AuthAPI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = IdentityStore(Path(self.directory.name) / 'identity.db')
        self.store.migrate()
        self.store.bootstrap('admin', 'password')
        app = FastAPI()
        app.include_router(auth_router(self.store, 'http://localhost', secure=False))
        self.client = TestClient(app, headers={'origin': 'http://localhost'})

    def login(self, username='admin', password='password'):
        return self.client.post('/auth/login', json={'username': username, 'password': password})

    def test_login_csrf_and_logout(self):
        self.assertEqual(self.login('admin', 'wrong').status_code, 401)
        self.assertEqual(self.login('unknown', 'wrong').status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        identity = self.client.get('/auth/me').json()
        self.assertEqual(identity['username'], 'admin')
        self.assertEqual(self.client.post('/auth/logout').status_code, 403)
        response = self.client.post('/auth/logout', headers={'x-csrf-token': identity['csrf']})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/auth/me').status_code, 401)

    def test_admin_and_student_permissions(self):
        self.login()
        csrf = self.client.get('/auth/me').json()['csrf']
        headers = {'x-csrf-token': csrf}
        response = self.client.post('/admin/users', json={'username': 'student', 'password': 'password'}, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        user_id = response.json()['id']
        self.assertEqual(self.client.post(f'/admin/users/{user_id}/reset-password', json={'password': 'new password'}, headers=headers).status_code, 204)
        self.assertEqual(self.client.post(f'/admin/users/{user_id}/reset-password', json={'password': 'password'}, headers=headers).status_code, 204)
        self.assertEqual(self.client.post('/admin/users', json={'username': 'student', 'password': 'password'}, headers=headers).status_code, 409)
        self.client.post('/auth/logout', headers=headers)
        self.login('student')
        self.assertEqual(self.client.get('/admin/users').status_code, 403)
        self.assertEqual(self.client.post('/auth/logout', headers={'origin': 'http://evil', 'x-csrf-token': 'bad'}).status_code, 403)
        self.client.cookies.clear()
        self.login()
        csrf = self.client.get('/auth/me').json()['csrf']
        self.assertEqual(self.client.patch('/admin/users/' + user_id, json={'is_active': False}, headers={'x-csrf-token': csrf}).status_code, 204)
        self.client.cookies.clear()
        self.assertEqual(self.login('student').status_code, 401)

    def test_rate_limit_and_origin(self):
        self.assertEqual(self.client.post('/auth/login', json={'username': 'admin', 'password': 'password'},
                                          headers={'origin': 'http://evil'}).status_code, 403)
        for _ in range(10):
            self.assertEqual(self.login('missing', 'bad').status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_successful_logins_do_not_clear_other_failures(self):
        for index in range(9):
            self.assertEqual(self.login(f'missing-{index}', 'bad').status_code, 401)
            self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.login('missing-final', 'bad').status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_secure_cookie_default(self):
        app = FastAPI()
        app.include_router(auth_router(self.store, 'https://localhost'))
        client = TestClient(app, base_url='https://localhost', headers={'origin': 'https://localhost'})
        response = client.post('/auth/login', json={'username': 'admin', 'password': 'password'})
        cookie = response.headers['set-cookie'].lower()
        self.assertIn('secure', cookie)
        self.assertIn('httponly', cookie)
        self.assertIn('samesite=lax', cookie)

    def test_password_change_and_replayed_cookie(self):
        self.assertEqual(self.login().status_code, 200)
        cookie = self.client.cookies.get('openlabscale_session')
        csrf = self.client.get('/auth/me').json()['csrf']
        response = self.client.post('/auth/change-password',
                                    json={'old_password': 'password', 'new_password': 'new password'},
                                    headers={'x-csrf-token': csrf})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/auth/me', headers={'cookie': f'openlabscale_session={cookie}'}).status_code, 401)
        self.assertEqual(self.login('admin', 'password').status_code, 401)
        self.assertEqual(self.login('admin', 'new password').status_code, 200)

    def test_expired_cookie_and_anonymous_admin(self):
        self.assertEqual(self.client.get('/admin/users').status_code, 401)
        self.login()
        cookie = self.client.cookies.get('openlabscale_session')
        import sqlite3
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute('UPDATE auth_sessions SET expires_at = 0')
        self.assertEqual(self.client.get('/auth/me', headers={'cookie': f'openlabscale_session={cookie}'}).status_code, 401)
