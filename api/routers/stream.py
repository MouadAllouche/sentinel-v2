"""Server-Sent Events stream (ids only; clients refetch)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.deps import current_user, db_path

router = APIRouter(prefix="/api", tags=["stream"])

MAX_CONNECTIONS_PER_USER = 3
_streams: dict[int, int] = {}


def _events(request: Request, after: int, user_id: int) -> Iterator[str]:
    from storage.ops_repository import list_changes

    _streams[user_id] = _streams.get(user_id, 0) + 1
    if _streams[user_id] > MAX_CONNECTIONS_PER_USER:
        _streams[user_id] -= 1
        yield 'event: error\ndata: {"code":"too_many_streams"}\n\n'
        return
    try:
        for tick in range(60):  # bounded to avoid a leaked generator in tests
            for row in list_changes(after, db_path=db_path(request)):
                after = int(row["id"])
                payload = {"type": row["kind"], "id": row["ref_id"], "at": row["at"]}
                yield f"id: {after}\ndata: {json.dumps(payload)}\n\n"
            if tick % 15 == 0:
                yield ": heartbeat\n\n"
            time.sleep(1)
    finally:
        _streams[user_id] -= 1


@router.get("/stream", response_model=None)
def stream(request: Request, user: dict[str, Any] = Depends(current_user)) -> StreamingResponse:
    header = request.headers.get("last-event-id", "0")
    try:
        after = max(0, int(header))
    except ValueError:
        after = 0
    return StreamingResponse(
        _events(request, after, int(user["id"])),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
