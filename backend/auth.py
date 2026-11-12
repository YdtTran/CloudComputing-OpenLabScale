from __future__ import annotations

import secrets
import sqlite3
import time
from collections import deque

import anyio
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .identity import IdentityStore

COOKIE = 'openlabscale_session'


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    old_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=1, max_length=1024)


class Activation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    is_active: bool


def current_user(store: IdentityStore, origin: str, request: Request, admin: bool = False, mutate: bool = False):
    token = request.cookies.get(COOKIE, '')
    user = store.session(token) if token else None
    if not user:
        raise HTTPException(401, 'Authentication required')
    if admin and user['role'] != 'admin':
        raise HTTPException(403, 'Administrator required')
    if mutate and (request.headers.get('origin') != origin or not secrets.compare_digest(
            request.headers.get('x-csrf-token', ''), user['csrf'])):
        raise HTTPException(403, 'Invalid request origin or CSRF token')
    return user


def auth_router(store: IdentityStore, origin: str, secure: bool = True) -> APIRouter:
    router = APIRouter()
    failures: dict[str, deque[float]] = {}
    limiter = anyio.CapacityLimiter(4)

    def current(request: Request, admin: bool = False, mutate: bool = False):
        return current_user(store, origin, request, admin, mutate)

    @router.post('/auth/login')
    async def login(body: Credentials, request: Request, response: Response):
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Invalid request origin')
        now = time.monotonic()
        keys = ('ip:' + (request.client.host if request.client else ''), 'user:' + body.username.casefold())
        for address in list(failures):
            while failures[address] and failures[address][0] <= now - 60:
                failures[address].popleft()
            if not failures[address]:
                del failures[address]
        if len(failures) + sum(key not in failures for key in keys) > 4096:
            raise HTTPException(429, 'Too many login attempts')
        attempts = [failures.setdefault(key, deque()) for key in keys]
        if any(len(attempt) >= 10 for attempt in attempts):
            raise HTTPException(429, 'Too many login attempts')
        for attempt in attempts:
            attempt.append(now)
        result = await anyio.to_thread.run_sync(store.login, body.username, body.password, limiter=limiter)
        if not result:
            raise HTTPException(401, 'Invalid username or password')
        for attempt in attempts:
            try:
                attempt.remove(now)
            except ValueError:
                pass
        token, _ = result
        response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite='lax', path='/')
        response.headers['Cache-Control'] = 'no-store'
        return {'ok': True}

    @router.get('/auth/me')
    async def me(request: Request, response: Response):
        response.headers['Cache-Control'] = 'no-store'
        return current(request)

    @router.post('/auth/logout', status_code=204)
    async def logout(request: Request, response: Response):
        current(request, mutate=True)
        store.logout(request.cookies[COOKIE])
        response.delete_cookie(COOKIE, path='/', secure=secure, httponly=True, samesite='lax')
        response.headers['Cache-Control'] = 'no-store'

    @router.post('/auth/change-password', status_code=204)
    async def change_password(body: PasswordChange, request: Request, response: Response):
        user = current(request, mutate=True)
        changed = await anyio.to_thread.run_sync(store.change_password, user['id'], body.old_password,
                                                  body.new_password, limiter=limiter)
        if not changed:
            raise HTTPException(401, 'Invalid credentials')
        response.delete_cookie(COOKIE, path='/', secure=secure, httponly=True, samesite='lax')
        response.headers['Cache-Control'] = 'no-store'

    @router.get('/admin/users')
    async def users(request: Request):
        current(request, admin=True)
        return store.users()

    @router.post('/admin/users', status_code=201)
    async def create_user(body: Credentials, request: Request):
        current(request, admin=True, mutate=True)
        try:
            user_id = await anyio.to_thread.run_sync(store.create_student, body.username, body.password, limiter=limiter)
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Username already exists')
        except ValueError as error:
            raise HTTPException(422, str(error))
        return {'id': user_id}

    @router.patch('/admin/users/{user_id}', status_code=204)
    async def set_active(user_id: str, body: Activation, request: Request):
        current(request, admin=True, mutate=True)
        try:
            updated = store.set_active(user_id, body.is_active)
        except ValueError as error:
            raise HTTPException(409, str(error))
        if not updated:
            raise HTTPException(404, 'User not found')

    @router.post('/admin/users/{user_id}/reset-password', status_code=204)
    async def reset_password(user_id: str, body: PasswordReset, request: Request):
        current(request, admin=True, mutate=True)
        updated = await anyio.to_thread.run_sync(store.reset_password, user_id, body.password, limiter=limiter)
        if not updated:
            raise HTTPException(404, 'Student not found')

    return router
