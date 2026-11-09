from __future__ import annotations

import asyncio
import json
import logging
import socket

from anyio import CancelScope
from fastapi import WebSocket, WebSocketDisconnect

from .scheduler import Entry

log = logging.getLogger(__name__)


async def bridge(websocket: WebSocket, entry: Entry, engine) -> None:
    sock = None
    marker = None
    tasks = []
    code = 1000
    try:
        opening = asyncio.create_task(asyncio.to_thread(engine.open_terminal, entry.session))
        try:
            terminal, marker, sock, initial = await asyncio.shield(opening)
        except asyncio.CancelledError:
            with CancelScope(shield=True):
                outcome, = await asyncio.gather(opening, return_exceptions=True)
            if isinstance(outcome, tuple):
                terminal, marker, sock, _ = outcome
            raise
        if entry.terminal_closed.is_set():
            return
        await websocket.accept(subprotocol="openlabscale")
        sock.setblocking(False)
        loop = asyncio.get_running_loop()

        async def output() -> None:
            if initial:
                await websocket.send_bytes(initial)
            while data := await loop.sock_recv(sock, 65536):
                await websocket.send_bytes(data)

        async def input_frames() -> None:
            nonlocal code
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    await loop.sock_sendall(sock, message["bytes"])
                    continue
                try:
                    frame = json.loads(message["text"])
                    rows, cols = frame["rows"], frame["cols"]
                    if type(rows) is not int or type(cols) is not int or not (1 <= rows <= 500 and 1 <= cols <= 500):
                        raise ValueError("invalid terminal size")
                except (TypeError, KeyError, ValueError):
                    code = 1003
                    return
                await asyncio.to_thread(engine.resize, terminal, rows, cols)

        tasks = [asyncio.create_task(coro) for coro in (output(), input_frames(), entry.terminal_closed.wait())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        code = 1011
        log.exception("Terminal failed for %s", entry.session.id)
    finally:
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            try:
                await websocket.close(code=code)
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass
            try:
                if marker and not entry.terminal_closed.is_set():
                    await asyncio.to_thread(engine.close_terminal, entry.session, marker)
            except Exception:
                log.exception("Terminal shell cleanup failed for %s", entry.session.id)
            finally:
                entry.terminal_attached = False
