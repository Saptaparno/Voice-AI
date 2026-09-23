"""Plivo API client — outbound call initiation via the Plivo Calls API."""

import base64

import requests

from app.config.plivo import load_plivo_credentials
from app.models import PlivoCallRequest


_PLIVO_API_BASE = "https://api.plivo.com/v1/Account"


def _auth_header() -> str:
    creds = load_plivo_credentials()
    token = base64.b64encode(
        f"{creds.auth_id}:{creds.auth_token}".encode()
    ).decode()
    return f"Basic {token}"


def make_call(request: PlivoCallRequest) -> dict:
    """Initiate an outbound call via the Plivo Calls API.

    POST https://api.plivo.com/v1/Account/{auth_id}/Call/

    Args:
        request: Validated ``PlivoCallRequest`` Pydantic model.

    Returns:
        dict: Parsed JSON from Plivo.  On success contains ``"request_uuid"``.

    Raises:
        RuntimeError: if credentials are not configured.
        requests.HTTPError: if Plivo returns a non-2xx response.
    """
    creds = load_plivo_credentials()

    url = f"{_PLIVO_API_BASE}/{creds.auth_id}/Call/"
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }
    payload = {
        "from": request.from_number,
        "to": request.to_number,
        "answer_url": request.answer_url,
        "answer_method": request.answer_method,
    }
    if request.hangup_url:
        payload["hangup_url"] = request.hangup_url
    if request.sip_headers:
        payload["sip_headers"] = request.sip_headers

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def hangup_call(call_uuid: str) -> dict:
    """Hang up a live call by its UUID.

    DELETE https://api.plivo.com/v1/Account/{auth_id}/Call/{call_uuid}/
    """
    creds = load_plivo_credentials()

    url = f"{_PLIVO_API_BASE}/{creds.auth_id}/Call/{call_uuid}/"
    headers = {"Authorization": _auth_header()}

    resp = requests.delete(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()
