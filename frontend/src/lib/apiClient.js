// 書き込み系/破壊的エンドポイント用のAPIキーをsessionStorageに保持し、
// リクエストへ付与するための薄いラッパー。タブ/セッションごとに自己発行するため
// localStorageではなくsessionStorageを使う(ブラウザ再起動をまたいで残さない)。
// EventSourceはカスタムヘッダーを送れないため、SSE系エンドポイントは
// withFreshToken() でクエリパラメータとしてトークンを付与する。

const STORAGE_KEY = 'mt_api_key';

export function getApiKey() {
    return sessionStorage.getItem(STORAGE_KEY) || '';
}

export function setApiKey(token) {
    if (token) {
        sessionStorage.setItem(STORAGE_KEY, token);
    }
}

async function issueApiToken() {
    const response = await fetch('/api/auth/token', { method: 'POST' });
    if (!response.ok) {
        throw new Error(`Failed to issue API token (status ${response.status})`);
    }
    const data = await response.json();
    setApiKey(data.token);
    return data.token;
}

// キャッシュ済みトークンがあればそれを返し、無ければ自己発行する。
export async function ensureApiKey() {
    const cached = getApiKey();
    if (cached) return cached;
    return issueApiToken();
}

// EventSource用: 常に新規トークンを強制発行してURLに埋め込む。
// SSE接続はユーザー操作起点(ボタンクリック)でしか始まらないため、
// 1回分のトークン発行の往復コストは無視できる。EventSourceはHTTPステータスを
// JSに渡さず接続後のURL/ヘッダー変更もできないため、401かどうかを検知して
// リトライする代わりに、接続直前に必ず有効なトークンを用意する。
export async function withFreshToken(url) {
    const token = await issueApiToken();
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}token=${encodeURIComponent(token)}`;
}

export async function apiFetch(url, options = {}) {
    const token = await ensureApiKey();
    const headers = token
        ? { ...(options.headers || {}), Authorization: `Bearer ${token}` }
        : (options.headers || {});
    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
        // サーバー再起動でapp.state.api_keysがリセットされた等でトークンが
        // 失効した場合、再発行して一度だけ透過的にリトライする。
        const freshToken = await issueApiToken();
        const retryHeaders = { ...(options.headers || {}), Authorization: `Bearer ${freshToken}` };
        return fetch(url, { ...options, headers: retryHeaders });
    }

    return response;
}
