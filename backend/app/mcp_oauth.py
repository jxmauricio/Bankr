"""OAuth 2.1 for the MCP connector, so Claude and ChatGPT can connect to /mcp
as a custom connector: the user signs in to Bankr, picks read or read +
write on a consent page, and can revoke the connection in Settings.

Follows the MCP authorization spec (rev. 2026-07-28):
- /mcp is the protected resource. A 401 from it points at the Protected
  Resource Metadata (RFC 9728), which names this backend as the
  authorization server.
- Authorization Server Metadata (RFC 8414) at the usual well-known path.
- Clients identify with a Client ID Metadata Document (an https URL as
  client_id, fetched on each authorization) or, for older clients, Dynamic
  Client Registration (RFC 7591). All clients are public: PKCE with S256 is
  required and there are no client secrets.
- Tokens are bound to the /mcp resource (RFC 8707) and the authorization
  response carries `iss` (RFC 9207).

Access tokens are short JWTs that name their grant (McpGrant), checked on
every request so a revoked connection stops at once. Refresh tokens are
opaque, stored hashed, and rotate on every use.

The legacy long-lived token from POST /auth/mcp-token still works (read
only); see app/auth.py.
"""

import base64
import hashlib
import ipaddress
import json
import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, verify_mcp_token
from app.config import settings
from app.db.base import get_db
from app.db.models import McpGrant, OAuthAuthorization, OAuthClient, User
from app.rate_limit import limit_auth_by_ip

MCP_PATH = "/mcp"
READ = "read"
WRITE = "write"
SCOPES = (READ, WRITE)
ACCESS_TOKEN_TYPE = "mcp_access"
AUTHORIZATION_TTL = timedelta(minutes=10)
MAX_REDIRECT_URIS = 10
MAX_CLIENT_METADATA_BYTES = 16_384

router = APIRouter(tags=["mcp-oauth"])


# --- URLs ---


def api_base(request: Request) -> str:
    """This backend's public origin: the OAuth issuer."""
    return (settings.public_api_url or str(request.base_url)).rstrip("/")


def resource_url(request: Request) -> str:
    """The canonical URI of the MCP server, which every token is bound to."""
    return api_base(request) + MCP_PATH


def resource_metadata_url(request: Request) -> str:
    return api_base(request) + "/.well-known/oauth-protected-resource" + MCP_PATH


def _same_resource(a: str, b: str) -> bool:
    """RFC 8707 resource comparison, lenient about a trailing slash and the
    case of the scheme and host."""
    pa, pb = urlsplit(a.rstrip("/")), urlsplit(b.rstrip("/"))
    return (pa.scheme.lower(), pa.netloc.lower(), pa.path) == (pb.scheme.lower(), pb.netloc.lower(), pb.path)


# --- Scopes ---


def parse_scope(value: str | None) -> set[str]:
    """Known scopes in a space-separated string; others (offline_access, ...)
    are ignored. write implies read."""
    scopes = {s for s in (value or "").split() if s in SCOPES}
    if WRITE in scopes:
        scopes.add(READ)
    return scopes


def format_scope(scopes: set[str]) -> str:
    return " ".join(s for s in SCOPES if s in scopes)


# --- Discovery ---


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata(request: Request) -> dict:
    return {
        "resource": resource_url(request),
        "authorization_servers": [api_base(request)],
        "scopes_supported": list(SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_name": "Bankr",
        "resource_documentation": settings.web_app_origin,
    }


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata(request: Request) -> dict:
    base = api_base(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "scopes_supported": list(SCOPES),
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
        "service_documentation": settings.web_app_origin,
    }


# --- Clients ---


def _is_loopback(uri: str) -> bool:
    parts = urlsplit(uri)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def _valid_redirect_uri(uri: str) -> bool:
    parts = urlsplit(uri)
    if parts.fragment or not parts.hostname:
        return False
    return parts.scheme == "https" or _is_loopback(uri)


def redirect_uri_matches(requested: str, registered: list[str]) -> bool:
    """Exact match, except that a loopback redirect matches on any port
    (RFC 8252 section 7.3): Claude Code and other native clients listen on a
    fresh port each time. Applied to localhost as well as the IP literals,
    as Claude Code's metadata declares both."""
    if requested in registered:
        return True
    if not _is_loopback(requested):
        return False
    req = urlsplit(requested)
    for uri in registered:
        reg = urlsplit(uri)
        if _is_loopback(uri) and (reg.hostname, reg.path, reg.query) == (req.hostname, req.path, req.query):
            return True
    return False


@dataclass
class ClientInfo:
    client_id: str
    client_name: str
    redirect_uris: list[str]


class ClientError(Exception):
    pass


def _public_host(hostname: str) -> bool:
    """Refuse to fetch metadata from private networks (SSRF)."""
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def fetch_client_metadata(url: str) -> dict:
    """GET a Client ID Metadata Document. Module-level so tests can swap it."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or not parts.path.strip("/"):
        raise ClientError("client_id URL must be https with a path")
    if not _public_host(parts.hostname):
        raise ClientError("client_id URL must be publicly reachable")
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_CLIENT_METADATA_BYTES:
                        raise ClientError("client metadata document is too large")
        return json.loads(body)
    except (httpx.HTTPError, ValueError) as e:
        raise ClientError(f"couldn't fetch client metadata: {e}") from e


def resolve_client(db: Session, client_id: str) -> ClientInfo:
    if client_id.startswith("https://"):
        doc = fetch_client_metadata(client_id)
        if not isinstance(doc, dict) or doc.get("client_id") != client_id:
            raise ClientError("client metadata document's client_id doesn't match its URL")
        uris = doc.get("redirect_uris")
        if not isinstance(uris, list) or not uris or not all(isinstance(u, str) for u in uris):
            raise ClientError("client metadata document has no redirect_uris")
        if doc.get("token_endpoint_auth_method", "none") != "none":
            raise ClientError("only public clients (token_endpoint_auth_method none) are supported")
        name = doc.get("client_name") if isinstance(doc.get("client_name"), str) else None
        return ClientInfo(client_id, (name or urlsplit(client_id).hostname or client_id)[:80], uris)

    row = db.get(OAuthClient, client_id)
    if row is None:
        raise ClientError("unknown client_id")
    return ClientInfo(row.client_id, row.client_name or "An MCP client", row.redirect_uris)


class RegisterRequest(BaseModel):
    redirect_uris: list[str]
    client_name: str | None = None
    token_endpoint_auth_method: str | None = None
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    scope: str | None = None


def _oauth_error(error: str, description: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/oauth/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_auth_by_ip)])
def register_client(body: RegisterRequest, db: Session = Depends(get_db)):
    """Dynamic Client Registration (RFC 7591), kept for clients that don't
    use Client ID Metadata Documents yet. Every client is public."""
    uris = body.redirect_uris
    if not uris or len(uris) > MAX_REDIRECT_URIS or not all(_valid_redirect_uri(u) for u in uris):
        return _oauth_error("invalid_redirect_uri", "redirect_uris must be https or loopback http URLs")
    if body.grant_types and not set(body.grant_types) <= {"authorization_code", "refresh_token"}:
        return _oauth_error("invalid_client_metadata", "only authorization_code and refresh_token are supported")

    client = OAuthClient(
        client_id="bankr_" + secrets.token_urlsafe(24),
        client_name=(body.client_name or "").strip()[:80] or None,
        redirect_uris=uris,
    )
    db.add(client)
    db.commit()
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_id_issued_at": int(client.created_at.timestamp()),
            "client_name": client.client_name,
            "redirect_uris": uris,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        status_code=status.HTTP_201_CREATED,
        headers={"Cache-Control": "no-store"},
    )


# --- Authorization ---


def _with_query(uri: str, params: dict) -> str:
    sep = "&" if urlsplit(uri).query else "?"
    return uri + sep + urlencode({k: v for k, v in params.items() if v is not None})


@router.get("/oauth/authorize")
def authorize(request: Request, db: Session = Depends(get_db)):
    """Validate the request, park it, and send the browser to the consent
    page in the web app. Until the redirect_uri is known good, errors are
    shown here instead of redirected (no open redirect)."""
    q = request.query_params
    client_id, redirect_uri = q.get("client_id", ""), q.get("redirect_uri", "")
    if not client_id or not redirect_uri:
        return _oauth_error("invalid_request", "client_id and redirect_uri are required")
    try:
        client = resolve_client(db, client_id)
    except ClientError as e:
        return _oauth_error("invalid_client", str(e))
    if not redirect_uri_matches(redirect_uri, client.redirect_uris):
        return _oauth_error("invalid_request", "redirect_uri isn't registered for this client")

    iss, state = api_base(request), q.get("state")

    def fail(error: str, description: str):
        return RedirectResponse(
            _with_query(redirect_uri, {"error": error, "error_description": description, "state": state, "iss": iss}),
            status_code=status.HTTP_302_FOUND,
        )

    if q.get("response_type") != "code":
        return fail("unsupported_response_type", "response_type must be code")
    if not q.get("code_challenge") or q.get("code_challenge_method") != "S256":
        return fail("invalid_request", "PKCE with code_challenge_method=S256 is required")
    resource = q.get("resource") or resource_url(request)
    if not _same_resource(resource, resource_url(request)):
        return fail("invalid_target", "resource must be this server's /mcp URL")
    requested = parse_scope(q.get("scope")) or {READ}

    pending = OAuthAuthorization(
        client_id=client.client_id,
        client_name=client.client_name,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=q["code_challenge"],
        requested_scope=format_scope(requested),
        resource=resource_url(request),
        expires_at=datetime.now(timezone.utc) + AUTHORIZATION_TTL,
    )
    db.add(pending)
    db.commit()
    return RedirectResponse(
        f"{settings.web_app_origin}/oauth/consent?{urlencode({'request': str(pending.id)})}",
        status_code=status.HTTP_302_FOUND,
    )


def _pending(db: Session, request_id: UUID) -> OAuthAuthorization:
    auth = db.get(OAuthAuthorization, request_id)
    if auth is None or auth.user_id is not None or auth.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This connection request has expired. Start again from your app.")
    return auth


@router.get("/oauth/requests/{request_id}")
def get_authorization_request(
    request_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """What the consent page shows: who is asking, for what, and where the
    browser goes next."""
    auth = _pending(db, request_id)
    redirect = urlsplit(auth.redirect_uri)
    return {
        "id": str(auth.id),
        "client_name": auth.client_name,
        "client_id": auth.client_id,
        "redirect_host": redirect.hostname,
        "redirect_is_loopback": _is_loopback(auth.redirect_uri),
        "requested_scopes": auth.requested_scope.split(),
        "account_email": user.email,
    }


class DecisionRequest(BaseModel):
    approve: bool
    write: bool = False  # read + write instead of read only


@router.post("/oauth/requests/{request_id}/decision")
def decide_authorization_request(
    request_id: UUID,
    body: DecisionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Approve (with the scope the user picked) or deny. Returns the URL to
    send the browser back to the client."""
    auth = _pending(db, request_id)
    params = {"state": auth.state, "iss": api_base(request)}
    if not body.approve:
        db.delete(auth)
        db.commit()
        return {"redirect_to": _with_query(auth.redirect_uri, {"error": "access_denied", **params})}

    grant = McpGrant(
        user_id=user.id,
        client_id=auth.client_id,
        client_name=auth.client_name,
        redirect_uri=auth.redirect_uri,
        scope=format_scope({READ, WRITE} if body.write else {READ}),
        resource=auth.resource,
    )
    db.add(grant)
    db.flush()
    code = secrets.token_urlsafe(32)
    auth.user_id = user.id
    auth.grant_id = grant.id
    auth.code_hash = _hash(code)
    auth.expires_at = datetime.now(timezone.utc) + AUTHORIZATION_TTL
    db.commit()
    return {"redirect_to": _with_query(auth.redirect_uri, {"code": code, **params})}


# --- Tokens ---


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pkce_ok(verifier: str, challenge: str) -> bool:
    if not 43 <= len(verifier) <= 128:
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return secrets.compare_digest(digest, challenge)


def _issue_tokens(request: Request, db: Session, grant: McpGrant) -> JSONResponse:
    now = datetime.now(timezone.utc)
    access_token = jwt.encode(
        {
            "typ": ACCESS_TOKEN_TYPE,
            "sub": str(grant.user_id),
            "gid": str(grant.id),
            "scope": grant.scope,
            "aud": grant.resource,
            "iss": api_base(request),
            "iat": now,
            "exp": now + timedelta(seconds=settings.mcp_access_token_ttl_seconds),
        },
        settings.session_jwt_secret,
        algorithm=settings.session_jwt_algorithm,
    )
    refresh_token = secrets.token_urlsafe(32)
    grant.refresh_token_hash = _hash(refresh_token)
    grant.last_used_at = now
    db.commit()
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.mcp_access_token_ttl_seconds,
            "refresh_token": refresh_token,
            "scope": grant.scope,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def _form(request: Request) -> dict[str, str]:
    """application/x-www-form-urlencoded body (RFC 6749), parsed by hand so
    the API needs no multipart dependency."""
    body = (await request.body()).decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


@router.post("/oauth/token")
async def token(request: Request, db: Session = Depends(get_db)):
    form = await _form(request)
    grant_type = form.get("grant_type")
    if grant_type == "authorization_code":
        return _exchange_code(request, db, form)
    if grant_type == "refresh_token":
        return _refresh(request, db, form)
    return _oauth_error("unsupported_grant_type", "grant_type must be authorization_code or refresh_token")


def _exchange_code(request: Request, db: Session, form: dict[str, str]):
    code = form.get("code", "")
    auth = db.query(OAuthAuthorization).filter(OAuthAuthorization.code_hash == _hash(code)).one_or_none() if code else None
    if auth is None or auth.grant_id is None:
        return _oauth_error("invalid_grant", "unknown authorization code")
    grant = db.get(McpGrant, auth.grant_id)
    if auth.used_at is not None:
        # A replayed code may mean it leaked: revoke what it already issued.
        if grant is not None and grant.revoked_at is None:
            grant.revoked_at = datetime.now(timezone.utc)
            grant.refresh_token_hash = None
            db.commit()
        return _oauth_error("invalid_grant", "authorization code was already used")
    if auth.expires_at <= datetime.now(timezone.utc):
        return _oauth_error("invalid_grant", "authorization code expired")
    if form.get("client_id") != auth.client_id:
        return _oauth_error("invalid_grant", "code was issued to another client")
    if form.get("redirect_uri", auth.redirect_uri) != auth.redirect_uri:
        return _oauth_error("invalid_grant", "redirect_uri doesn't match the authorization request")
    if not _pkce_ok(form.get("code_verifier", ""), auth.code_challenge):
        return _oauth_error("invalid_grant", "PKCE verification failed")
    if form.get("resource") and not _same_resource(form["resource"], auth.resource):
        return _oauth_error("invalid_target", "resource doesn't match the authorization request")
    if grant is None or grant.revoked_at is not None:
        return _oauth_error("invalid_grant", "this connection was revoked")

    auth.used_at = datetime.now(timezone.utc)
    return _issue_tokens(request, db, grant)


def _refresh(request: Request, db: Session, form: dict[str, str]):
    refresh_token = form.get("refresh_token", "")
    grant = (
        db.query(McpGrant).filter(McpGrant.refresh_token_hash == _hash(refresh_token)).one_or_none()
        if refresh_token
        else None
    )
    if grant is None or grant.revoked_at is not None:
        return _oauth_error("invalid_grant", "refresh token is invalid or was revoked")
    if form.get("client_id") and form["client_id"] != grant.client_id:
        return _oauth_error("invalid_grant", "refresh token was issued to another client")
    if form.get("resource") and not _same_resource(form["resource"], grant.resource):
        return _oauth_error("invalid_target", "resource doesn't match this connection")
    return _issue_tokens(request, db, grant)


@router.post("/oauth/revoke")
async def revoke(request: Request, db: Session = Depends(get_db)):
    """RFC 7009. Either token revokes the whole connection. Always 200."""
    value = (await _form(request)).get("token", "")
    grant = db.query(McpGrant).filter(McpGrant.refresh_token_hash == _hash(value)).one_or_none() if value else None
    if grant is None and value:
        claims = _access_claims(value)
        grant = db.get(McpGrant, UUID(claims["gid"])) if claims else None
    if grant is not None:
        _revoke(db, grant)
    return JSONResponse({}, headers={"Cache-Control": "no-store"})


def _revoke(db: Session, grant: McpGrant) -> None:
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
    grant.refresh_token_hash = None
    db.commit()


# --- Checking tokens at /mcp ---


@dataclass
class McpCaller:
    user_id: UUID
    scopes: set[str]
    grant_id: UUID | None  # None for the legacy minted token
    client_name: str


def _access_claims(token: str, audience: str | None = None) -> dict | None:
    try:
        claims = jwt.decode(
            token,
            settings.session_jwt_secret,
            algorithms=[settings.session_jwt_algorithm],
            options={"verify_aud": False},
        )
    except (JWTError, ExpiredSignatureError):
        return None
    if claims.get("typ") != ACCESS_TOKEN_TYPE or "gid" not in claims:
        return None
    if audience is not None and not _same_resource(str(claims.get("aud", "")), audience):
        return None
    return claims


def authenticate_mcp(db: Session, token: str, resource: str) -> McpCaller | None:
    """Who is calling /mcp, with which scopes; None if the token isn't one
    this server issued for itself, or its connection was revoked."""
    legacy_user = verify_mcp_token(token)
    if legacy_user is not None:
        return McpCaller(legacy_user, {READ}, None, "MCP token")

    claims = _access_claims(token, audience=resource)
    if claims is None:
        return None
    try:
        grant = db.get(McpGrant, UUID(claims["gid"]))
    except ValueError:
        return None
    if grant is None or grant.revoked_at is not None or str(grant.user_id) != claims.get("sub"):
        return None
    now = datetime.now(timezone.utc)
    if grant.last_used_at is None or now - grant.last_used_at > timedelta(minutes=5):
        grant.last_used_at = now
        db.commit()
    # The grant's scope, not the token's: narrowing takes effect at once.
    return McpCaller(grant.user_id, parse_scope(grant.scope) & parse_scope(claims.get("scope")), grant.id, grant.client_name)


# --- Connected apps (Settings) ---


def _grant_dict(grant: McpGrant) -> dict:
    return {
        "id": str(grant.id),
        "client_name": grant.client_name,
        "scopes": grant.scope.split(),
        "redirect_host": urlsplit(grant.redirect_uri).hostname,
        "created_at": grant.created_at.isoformat(),
        "last_used_at": grant.last_used_at.isoformat() if grant.last_used_at else None,
    }


@router.get("/mcp/grants")
def list_grants(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Connected apps, plus the URL to paste into Claude or ChatGPT."""
    grants = (
        db.query(McpGrant)
        .filter(McpGrant.user_id == user.id, McpGrant.revoked_at.is_(None), McpGrant.refresh_token_hash.isnot(None))
        .order_by(McpGrant.created_at.desc())
        .all()
    )
    return {"server_url": resource_url(request), "grants": [_grant_dict(g) for g in grants]}


@router.delete("/mcp/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_grant(grant_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    grant = db.get(McpGrant, grant_id)
    if grant is None or grant.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    _revoke(db, grant)
