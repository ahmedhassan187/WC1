from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import get_settings


def get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key)


def create_session_token(access_token: str, refresh_token: str) -> str:
    serializer = get_serializer()
    return serializer.dumps({"access": access_token, "refresh": refresh_token})


def decode_session_token(token: str) -> dict | None:
    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=60 * 60 * 24 * 7)
        return data
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    data = decode_session_token(token)
    if not data:
        return None
    try:
        from app.database import get_supabase
        sb = get_supabase()
        sb.auth.set_session(data["access"], data["refresh"])
        user = sb.auth.get_user()
        if user and user.user:
            return {"id": user.user.id, "email": user.user.email}
    except Exception:
        return None
    return None


def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_auth_redirect(request: Request) -> RedirectResponse | dict:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return user
