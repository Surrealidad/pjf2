"""HTTP helpers. Never raise: failures come back as status 0 or an HTTP code."""
import json
import urllib.error
import urllib.request

UA = "PJF/2.0 (personal job search tool; ministral.dev)"


def get(url, timeout=20, accept="*/*", data=None):
    """Return (status, body_bytes). With data (bytes), sends a JSON POST."""
    headers = {"User-Agent": UA, "Accept": accept}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(10_000_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:  # timeouts, DNS, TLS, resets
        return 0, b""


def get_json(url, timeout=20):
    """Return (status, parsed_json_or_None)."""
    status, body = get(url, timeout, "application/json")
    if status != 200:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return status, None


def post_json(url, body, timeout=20):
    """POST a JSON body, return (status, parsed_json_or_None)."""
    status, raw = get(url, timeout, "application/json", data=json.dumps(body).encode())
    if status != 200:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return status, None
