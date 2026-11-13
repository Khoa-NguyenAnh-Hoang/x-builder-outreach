"""OAuth 2.0 Authorization Code + PKCE for X (T07).

Implements the documented flow (docs.x.com fundamentals/authentication):
authorize URL with S256 challenge → user approves in browser → code lands on the
redirect URL → exchange for token (2 h) → store locally → refresh when near expiry.

CLI (interactive, once per machine): `uv run python -m src.integrations.x_auth`
The redirect never needs a local server: after approving, the browser lands on a
dead 127.0.0.1 URL whose address bar contains the code — paste that full URL back.

Secrets policy (I9): the verifier, tokens and secrets are never printed, never
committed; tokens persist only in data/ (gitignored).
"""

import base64
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from src.integrations.x_client import AuthenticationError, MalformedResponseError, RequestTimeout

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = "tweet.read users.read dm.read dm.write offline.access"
TOKENS_PATH = Path("data/tokens.json")
SESSION_PATH = Path("data/auth_session.json")


def generate_pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) — verifier 43–128 chars, challenge S256."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, state: str,
                        code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "s256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def validate_state(expected: str, received: str | None) -> None:
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise AuthenticationError(
            "OAuth state mismatch — restart the auth flow (the request may be tampered)"
        )


def extract_code(pasted: str) -> str:
    """Accept either the full redirect URL or a bare authorization code."""
    s = pasted.strip()
    if "error=" in s:
        qs = parse_qs(urlparse(s).query)
        reason = (qs.get("error") or ["unknown"])[0]
        raise AuthenticationError(f"authorize returned error: {reason}")
    if "code=" in s:
        qs = parse_qs(urlparse(s).query)
        if "code" not in qs or not qs["code"][0]:
            raise AuthenticationError("redirect URL contained no authorization code")
        return qs["code"][0]
    return s


def _token_request(payload: dict, client_id: str, client_secret: str | None,
                   transport: httpx.BaseTransport | None = None) -> dict:
    headers = {}
    if client_secret:
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"
    try:
        # top-level httpx.post can't take a transport — use an explicit Client
        with httpx.Client(timeout=30, transport=transport) as client:
            resp = client.post(TOKEN_URL, data=payload, headers=headers)
    except httpx.TimeoutException as err:
        raise RequestTimeout(f"token endpoint timeout: {err}") from err
    except httpx.HTTPError as err:
        raise AuthenticationError(f"token endpoint unreachable: {err}") from err
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error_description", resp.text[:160])
        except ValueError:
            detail = resp.text[:160]
        raise AuthenticationError(f"token exchange failed ({resp.status_code}): {detail}")
    try:
        body = resp.json()
        if not body.get("access_token"):
            raise KeyError("access_token")
    except ValueError as err:
        raise MalformedResponseError("token endpoint returned non-JSON") from err
    except KeyError as err:
        raise MalformedResponseError(f"token response missing {err}") from err
    return body


def exchange_code(client_id: str, client_secret: str | None, code: str,
                  redirect_uri: str, code_verifier: str,
                  transport: httpx.BaseTransport | None = None) -> dict:
    return _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "client_id": client_id,
    }, client_id, client_secret, transport)


def refresh_access_token(client_id: str, client_secret: str | None, refresh: str,
                         transport: httpx.BaseTransport | None = None) -> dict:
    return _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
    }, client_id, client_secret, transport)


def save_tokens(tokens: dict, path: Path | None = None) -> None:
    path = Path(path) if path else TOKENS_PATH  # resolve at call time (patchable)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": (datetime.now(UTC)
                       + timedelta(seconds=int(tokens.get("expires_in", 7200)))
                       ).isoformat(timespec="seconds"),
        "scope": tokens.get("scope", SCOPES),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_tokens(path: Path | None = None) -> dict | None:
    path = Path(path) if path else TOKENS_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_fresh_tokens(client_id: str, client_secret: str | None,
                        tokens: dict | None = None,
                        transport: httpx.BaseTransport | None = None,
                        path: Path | None = None) -> dict | None:
    """Return usable tokens, refreshing when within 60 s of expiry. None if never authorized."""
    if tokens is None:
        tokens = load_tokens(path)
    if tokens is None:
        return None
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now(UTC) < expires_at - timedelta(seconds=60):
        return tokens
    if not tokens.get("refresh_token"):
        raise AuthenticationError(
            "access token expired and no refresh token stored — re-run: "
            "uv run python -m src.integrations.x_auth"
        )
    fresh = refresh_access_token(client_id, client_secret, tokens["refresh_token"], transport)
    save_tokens(fresh, path)
    return load_tokens(path)


def main() -> int:  # interactive CLI: `uv run python -m src.integrations.x_auth`
    from src.config import get_settings

    settings = get_settings()
    if not settings.x_client_id:
        print("Missing X_CLIENT_ID in .env — copy .env.example to .env and fill it in.")
        return 1
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps({"state": state, "code_verifier": verifier}),
                            encoding="utf-8")

    print("1) Open this URL in a browser ONCE, approve, then IMMEDIATELY copy the FULL")
    print("   URL of the page you land on (it will fail to load — that is expected).")
    print("   X codes are single-use and expire fast — do not re-open the link after approving.")
    print()
    print(build_authorize_url(settings.x_client_id, settings.oauth_callback_url,
                              state, challenge))
    print()

    for attempt in range(1, 4):  # a consumed/expired code just needs a fresh approval
        pasted = input(f"2) Paste the redirect URL (or bare code) [attempt {attempt}/3]: ")
        try:
            code = extract_code(pasted)
            received = None
            if "state=" in pasted:
                received = parse_qs(urlparse(pasted).query).get("state", [None])[0]
            validate_state(state, received)
            tokens = exchange_code(settings.x_client_id, settings.x_client_secret, code,
                                   settings.oauth_callback_url, verifier)
        except AuthenticationError as err:
            print(f"   ✗ attempt {attempt} failed: {err}")
            print("     → approve the SAME link again (fresh code) and paste the new URL right away.")
            continue
        save_tokens(tokens)
        print("Authorized. Access token stored in data/tokens.json — never printed, never committed.")
        print("Scope granted:", tokens.get("scope", SCOPES))
        return 0
    print("Three failed attempts — start over with `uv run python -m src.integrations.x_auth`.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
