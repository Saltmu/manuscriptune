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
