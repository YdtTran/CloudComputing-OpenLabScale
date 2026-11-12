from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import secrets
import sqlite3
from contextlib import closing
import time
import uuid
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_DUMMY_HASH = '$argon2id$v=19$m=65536,t=3,p=4$MDEyMzQ1Njc4OWFiY2RlZg$wNUEMuWYkLiu++HWHh7uj1tRS6nW33kpxITuLj6T3cc'


class IdentityStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def migrate(self) -> None:
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('Identity database version is newer than this application')
            if version == 0:
                connection.execute('''CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('student', 'admin')),
                        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )''')
                connection.execute('PRAGMA user_version = 1')
            if version < 2:
                connection.execute('''CREATE TABLE auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )''')
                connection.execute('PRAGMA user_version = 2')

    def bootstrap(self, username: str, password: str) -> str:
        if not username.strip() or not password:
            raise ValueError('Username and password are required')
        password_hash = PasswordHasher().hash(password)
        user_id = str(uuid.uuid4())
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise ValueError('Identity database already has users')
            connection.execute(
                'INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)',
                (user_id, username, password_hash, 'admin'),
            )
        return user_id

    def login(self, username: str, password: str):
        with closing(self.connect()) as connection, connection:
            user = connection.execute(
                'SELECT id, password_hash, is_active FROM users WHERE username = ?', (username,)
            ).fetchone()
        try:
            valid = PasswordHasher().verify(user[1] if user else _DUMMY_HASH, password)
        except VerifyMismatchError:
            return None
        if not valid or not user or not user[2]:
            return None
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            current = connection.execute(
                'SELECT password_hash, is_active FROM users WHERE id = ?', (user[0],)
            ).fetchone()
            if current != (user[1], 1):
                return None
            connection.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (time.time(),))
            connection.execute(
                'INSERT INTO auth_sessions VALUES (?, ?, ?, ?)',
                (hashlib.sha256(token.encode()).hexdigest(), user[0], csrf, time.time() + 8 * 3600),
            )
        return token, csrf

    def session(self, token: str):
        with closing(self.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute('''SELECT users.id, users.username, users.role, auth_sessions.csrf
                FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ? AND users.is_active = 1''',
                (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token: str) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute('DELETE FROM auth_sessions WHERE token_hash = ?',
                               (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        if not new_password:
            raise ValueError('Password is required')
        with closing(self.connect()) as connection, connection:
            user = connection.execute('SELECT password_hash FROM users WHERE id = ? AND is_active = 1',
                                      (user_id,)).fetchone()
        if not user:
            return False
        try:
            PasswordHasher().verify(user[0], old_password)
        except VerifyMismatchError:
            return False
        password_hash = PasswordHasher().hash(new_password)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            result = connection.execute('''UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND is_active = 1 AND password_hash = ?''', (password_hash, user_id, user[0]))
            if result.rowcount != 1:
                return False
            connection.execute('DELETE FROM auth_sessions WHERE user_id = ?', (user_id,))
        return True

    def create_student(self, username: str, password: str) -> str:
        if not username.strip() or not password:
            raise ValueError('Username and password are required')
        user_id = str(uuid.uuid4())
        password_hash = PasswordHasher().hash(password)
        with closing(self.connect()) as connection, connection:
            connection.execute('INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)',
                               (user_id, username, password_hash, 'student'))
        return user_id

    def users(self):
        with closing(self.connect()) as connection, connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(
                'SELECT id, username, role, is_active, created_at, updated_at FROM users ORDER BY username'
            )]

    def set_active(self, user_id: str, active: bool) -> bool:
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            user = connection.execute('SELECT role, is_active FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return False
            if not active and user == ('admin', 1):
                count = connection.execute("SELECT count(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
                if count == 1:
                    raise ValueError('Cannot deactivate the last active administrator')
            connection.execute('UPDATE users SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                               (int(active), user_id))
            if not active:
                connection.execute('DELETE FROM auth_sessions WHERE user_id = ?', (user_id,))
        return True

    def reset_password(self, user_id: str, password: str) -> bool:
        if not password:
            raise ValueError('Password is required')
        password_hash = PasswordHasher().hash(password)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            result = connection.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND role = 'student'",
                                        (password_hash, user_id))
            if result.rowcount != 1:
                return False
            connection.execute('DELETE FROM auth_sessions WHERE user_id = ?', (user_id,))
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description='Bootstrap the initial OpenLabScale administrator')
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Administrator password: ')
    if password != getpass.getpass('Repeat password: '):
        parser.error('Passwords do not match')
    store = IdentityStore(args.database)
    store.migrate()
    store.bootstrap(args.username, password)


if __name__ == '__main__':
    main()
