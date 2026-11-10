import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.identity import IdentityStore
from backend.models import Settings
from backend_tests.test_api import Docker


class SessionAuthorization(unittest.TestCase):
    def test_workspace_authorization_uses_login_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'users.db')
            store = IdentityStore(Path(database))
            store.migrate()
            store.bootstrap('admin', 'password')
            alice = store.create_student('alice', 'password')
            store.create_student('bob', 'password')
            settings = Settings(deployment='test', identity_database=database, secure_cookie=False,
                                terminal_origin='http://127.0.0.1:8000', poll_seconds=0.02)
            with TestClient(create_app(settings, Docker()), headers={'origin': settings.terminal_origin}) as client:
                self.assertEqual(client.post('/sessions', json={}).status_code, 401)
                self.assertEqual(client.post('/auth/login', json={'username': 'alice', 'password': 'password'}).status_code, 200)
                self.assertEqual(client.get('/settings').status_code, 403)
                self.assertEqual(client.get('/workspace/summary').json()['available_slots'], 2)
                csrf = client.get('/auth/me').json()['csrf']
                self.assertEqual(client.post('/sessions', json={}).status_code, 403)
                response = client.post('/sessions', json={}, headers={'x-csrf-token': csrf})
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(response.json()['owner'], alice)
                session_id = response.json()['id']
                self.assertEqual(client.get('/stats').status_code, 403)
                client.cookies.clear()
                self.assertEqual(client.post('/auth/login', json={'username': 'bob', 'password': 'password'}).status_code, 200)
                self.assertEqual(client.get('/sessions/' + session_id).status_code, 404)
                self.assertEqual(client.get('/sessions').json(), [])
                client.cookies.clear()
                self.assertEqual(client.post('/auth/login', json={'username': 'admin', 'password': 'password'}).status_code, 200)
                self.assertEqual(client.get('/stats').status_code, 200)
                self.assertEqual(client.get('/stats').json()['accounts'], {'total': 3, 'active': 3})
                self.assertEqual(client.get('/settings').json()['per_user'], 2)
                self.assertEqual(client.get('/sessions/' + session_id).status_code, 403)
