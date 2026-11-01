"""SweetYaar logs API (Cloud Run function `logs-api`): the parent app uploads
the toy's log sectors here; only this function writes to Firestore.

    GET  /v1/devices/{id}/latest      where the toy's uploads stand (404: none)
    POST /v1/devices/{id}/sectors     whole sectors, application/octet-stream
         ?open=<seq>      the last sector is still being written
         &replaces=<n>    the toy's log no longer continues history n
         &app=<version>

Upload rules are in uploads.py; deployment in docs/logging-and-debugging.md.
"""

from __future__ import annotations

import datetime as dt
import os

import functions_framework
from google.cloud import firestore

import uploads

ALLOWED_ORIGINS = set(filter(None, os.environ.get(
    "ALLOWED_ORIGINS", "https://sweetyaar.zachmoshe.com,http://localhost:8000").split(",")))
MAX_BODY = uploads.MAX_UPLOAD_SECTORS * uploads.SECTOR_SIZE

_client: firestore.Client | None = None


def client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not value.isdigit() or len(value) > 10:
        raise uploads.UploadError(400, "invalid number")
    return int(value)


def latest(device: str) -> tuple[dict, int]:
    snapshot = client().collection("devices").document(device).get()
    if not snapshot.exists:
        return {"error": "nothing uploaded yet"}, 404
    return uploads.Device.from_doc(snapshot.to_dict()).public(), 200


def upload(device: str, request) -> tuple[dict, int]:
    if (request.content_length or 0) > MAX_BODY:
        raise uploads.UploadError(413, f"at most {uploads.MAX_UPLOAD_SECTORS} sectors per upload")
    sectors = uploads.split_sectors(request.get_data(cache=False), device)
    open_seq = optional_int(request.args.get("open"))
    replaces = optional_int(request.args.get("replaces"))
    app = request.args.get("app", "")
    now = dt.datetime.now(dt.timezone.utc)
    db = client()
    device_ref = db.collection("devices").document(device)

    def chunk_ref(history: int, chunk: int):
        return device_ref.collection("chunks").document(uploads.chunk_id(history, chunk))

    @firestore.transactional
    def run(transaction) -> uploads.Plan:
        snapshot = device_ref.get(transaction=transaction)
        current = uploads.Device.from_doc(snapshot.to_dict()) if snapshot.exists else None
        tail = b""
        if current:
            tail_snapshot = chunk_ref(current.history, current.chunk).get(transaction=transaction)
            if tail_snapshot.exists:
                tail = tail_snapshot.get("data")
        plan = uploads.plan_upload(current, tail, sectors, open_seq=open_seq, replaces=replaces,
                                   now=now, app=app)
        for number, data in plan.chunks.items():
            transaction.set(chunk_ref(plan.device.history, number), uploads.chunk_doc(data, now))
        transaction.set(device_ref, plan.device.to_doc())
        return plan

    plan = run(db.transaction())
    print(f"upload device={device} sectors={len(sectors)} accepted={plan.accepted} "
          f"history={plan.device.history} seq={plan.device.seq} app={app[:40]}")
    return {**plan.device.public(), "accepted": plan.accepted}, 200


@functions_framework.http
def logs_api(request):
    origin = request.headers.get("Origin", "")
    headers = {"Cache-Control": "no-store"}
    if origin in ALLOWED_ORIGINS:
        headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
    if request.method == "OPTIONS":
        headers.update({
            "Access-Control-Allow-Methods": "GET, POST",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        })
        return "", 204, headers
    parts = request.path.strip("/").split("/")
    try:
        if len(parts) != 4 or parts[:2] != ["v1", "devices"]:
            raise uploads.UploadError(404, "not found")
        device = uploads.parse_device(parts[2])
        if parts[3] == "latest" and request.method == "GET":
            body, status = latest(device)
        elif parts[3] == "sectors" and request.method == "POST":
            body, status = upload(device, request)
        else:
            raise uploads.UploadError(404, "not found")
    except uploads.UploadError as error:
        body, status = {"error": str(error)}, error.status
    return body, status, headers
