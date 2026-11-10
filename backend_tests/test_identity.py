import sqlite3
from contextlib import closing
import os
import tempfile
import unittest
from pathlib import Path

from backend.identity import IdentityStore


class IdentityStoreTests(unittest.TestCase):
    def test_migration_and_bootstrap_are_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.db'
            store = IdentityStore(path)
            store.migrate()
            store.migrate()
            user_id = store.bootstrap('admin', 'a suitable password')
            with closing(sqlite3.connect(path)) as connection, connection:
                row = connection.execute('SELECT id, username, password_hash, role FROM users').fetchone()
            self.assertEqual((row[0], row[1], row[3]), (user_id, 'admin', 'admin'))
            self.assertTrue(row[2].startswith('$argon2id$'))
            self.assertNotIn('a suitable password', row[2])
            with self.assertRaises(ValueError):
                IdentityStore(path).bootstrap('another', 'a different password')
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def test_database_permissions_and_unique_usernames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.db'
            store = IdentityStore(path)
            store.migrate()
            store.bootstrap('admin', 'password')
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with closing(sqlite3.connect(path)) as connection, connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO users (id, username, password_hash, role) VALUES ('other', 'admin', 'hash', 'student')"
                    )

    def test_newer_schema_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.db'
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('PRAGMA user_version = 3')
            with self.assertRaises(RuntimeError):
                IdentityStore(path).migrate()
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_login_session_revocation_and_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = IdentityStore(Path(directory) / 'identity.db')
            store.migrate()
            user_id = store.bootstrap('admin', 'password')
            self.assertIsNone(store.login('admin', 'wrong'))
            self.assertIsNone(store.login('unknown', 'wrong'))
            token, csrf = store.login('admin', 'password')
            self.assertEqual(store.session(token)['id'], user_id)
            self.assertEqual(store.session(token)['csrf'], csrf)
            with closing(sqlite3.connect(store.path)) as connection, connection:
                self.assertNotEqual(connection.execute('SELECT token_hash FROM auth_sessions').fetchone()[0], token)
                connection.execute('UPDATE auth_sessions SET expires_at = 0')
            self.assertIsNone(store.session(token))
            token, _ = store.login('admin', 'password')
            store.logout(token)
            self.assertIsNone(store.session(token))

    def test_password_change_revokes_all_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = IdentityStore(Path(directory) / 'identity.db')
            store.migrate()
            user_id = store.bootstrap('admin', 'password')
            first, _ = store.login('admin', 'password')
            second, _ = store.login('admin', 'password')
            self.assertFalse(store.change_password(user_id, 'wrong', 'new password'))
            self.assertIsNotNone(store.session(first))
            self.assertTrue(store.change_password(user_id, 'password', 'new password'))
            self.assertIsNone(store.session(first))
            self.assertIsNone(store.session(second))
            self.assertIsNone(store.login('admin', 'password'))
            self.assertIsNotNone(store.login('admin', 'new password'))

    def test_student_management_revokes_access(self):
        with tempfile.TemporaryDirectory() as directory:
            store = IdentityStore(Path(directory) / 'identity.db')
            store.migrate()
            admin_id = store.bootstrap('admin', 'password')
            student_id = store.create_student('student', 'password')
            with self.assertRaises(sqlite3.IntegrityError):
                store.create_student('student', 'another password')
            self.assertEqual({user['username'] for user in store.users()}, {'admin', 'student'})
            token, _ = store.login('student', 'password')
            self.assertTrue(store.set_active(student_id, False))
            self.assertIsNone(store.session(token))
            self.assertIsNone(store.login('student', 'password'))
            self.assertTrue(store.set_active(student_id, True))
            token, _ = store.login('student', 'password')
            self.assertTrue(store.reset_password(student_id, 'new password'))
            self.assertIsNone(store.session(token))
            self.assertIsNone(store.login('student', 'password'))
            self.assertIsNotNone(store.login('student', 'new password'))
            with self.assertRaises(ValueError):
                store.set_active(admin_id, False)
