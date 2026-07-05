import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _effective_port(scheme: str, port: int | None) -> int | None:
    return port if port is not None else _DEFAULT_PORTS.get(scheme)


async def verify_local_origin(request: Request) -> None:
    """Origin/Refererヘッダーが同一オリジンでないリクエストを拒否する。

    両ヘッダーが欠落している場合(EventSourceの単純GETやcurl/テスト等)は許可する。
    """
    header = request.headers.get("origin") or request.headers.get("referer")
    if not header:
        return

    parsed = urlsplit(header)
    same_host = parsed.hostname == request.url.hostname
    same_port = _effective_port(parsed.scheme, parsed.port) == _effective_port(
        request.url.scheme, request.url.port
    )
    if not (same_host and same_port):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")


async def require_api_key(request: Request) -> None:
    """書き込み系/破壊的操作エンドポイントをAPIキーで保護する。

    app.state.api_key が未設定の場合(review_server.main()を経由しないテスト実行時等)は
    認証を無効化する。EventSourceはカスタムヘッダーを送れないため、
    クエリパラメータ ?token=... でのトークン受け渡しも許可する。
    """
    expected = getattr(request.app.state, "api_key", None)
    if not expected:
        return

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        supplied = auth_header.removeprefix("Bearer ").strip()
    else:
        supplied = request.query_params.get("token", "")

    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
