"""Regression for the November 2026 broken preview and download responses."""

import asyncio
import gzip
from pathlib import Path

import pytest
from starlette.applications import Starlette
from streamlit.runtime.media_file_storage import MediaFileKind
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
from streamlit.web.server.starlette.starlette_gzip_middleware import SelectiveGZipMiddleware
from streamlit.web.server.starlette.starlette_routes import create_media_routes

from shieldlab.room import diagram, report_room
from shieldlab.room.engines import AnalyticalEngine
from shieldlab.room.model import RoomDesign


@pytest.fixture(scope="module")
def room_media():
    design = RoomDesign.from_json(
        (Path(__file__).parent / "golden_room.json").read_text(encoding="utf-8")
    )
    results = AnalyticalEngine(design).evaluate_all("design")
    plan = diagram.render(design, results)
    report = report_room.build_report(design, results, "design", plan)
    return {
        "plan": (plan, "image/png", MediaFileKind.MEDIA, None),
        "report": (
            report_room.to_xlsx(report),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            MediaFileKind.DOWNLOADABLE,
            "room.xlsx",
        ),
    }


async def _media_response(storage, url, encoding):
    server = Starlette(routes=create_media_routes(storage, ""))
    server.add_middleware(SelectiveGZipMiddleware)
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": url, "query_string": b"",
        "root_path": "", "headers": [(b"accept-encoding", encoding.encode())],
        "server": ("localhost", 8501), "client": ("127.0.0.1", 12345),
    }
    await server(scope, receive, send)
    return messages


@pytest.mark.parametrize("media_name", ["plan", "report"])
@pytest.mark.parametrize("encoding", ["gzip", "identity"])
def test_generated_room_media_is_served_without_server_errors(room_media, media_name, encoding):
    content, mimetype, kind, filename = room_media[media_name]
    storage = MemoryMediaFileStorage("/media")
    file_id = storage.load_and_get_id(content, mimetype, kind, filename)
    messages = asyncio.run(_media_response(storage, storage.get_url(file_id), encoding))

    # Starlette 1.10 + Streamlit 1.58 sent a body without response headers, causing HTTP 500.
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    headers = dict(messages[0]["headers"])
    body = b"".join(message.get("body", b"") for message in messages[1:])
    if headers.get(b"content-encoding") == b"gzip":
        body = gzip.decompress(body)
    assert body == content
    assert headers[b"content-type"].decode() == mimetype
    if filename:
        assert filename.encode() in headers[b"content-disposition"]
