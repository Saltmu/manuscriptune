// 書き込み系/破壊的エンドポイント用のAPIキーをlocalStorageに保持し、
// リクエストへ付与するための薄いラッパー。
// EventSourceはカスタムヘッダーを送れないため、SSE系エンドポイントには
// withToken() でクエリパラメータとしてトークンを付与する。

const STORAGE_KEY = 'mt_api_key';

export function getApiKey() {
    return localStorage.getItem(STORAGE_KEY) || '';
}

export function setApiKey(token) {
    if (token) {
        localStorage.setItem(STORAGE_KEY, token);
    }
}

export function withToken(url) {
    const token = getApiKey();
    if (!token) return url;
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}token=${encodeURIComponent(token)}`;
}

export function apiFetch(url, options = {}) {
    const token = getApiKey();
    if (!token) {
        return fetch(url, options);
    }
    const headers = { ...(options.headers || {}), Authorization: `Bearer ${token}` };
    return fetch(url, { ...options, headers });
}
