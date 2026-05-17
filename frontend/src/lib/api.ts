/**
 * API client — thin wrapper around fetch for all backend calls.
 * Handles automatic JWT refresh on 401 responses.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ── Token helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
}

function getRefreshToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
}

function setTokens(accessToken: string, refreshToken: string) {
  localStorage.setItem("access_token", accessToken);
  localStorage.setItem("refresh_token", refreshToken);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

// ── Refresh logic ─────────────────────────────────────────────────────────────

let _isRefreshing = false;
let _refreshQueue: Array<(token: string | null) => void> = [];

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  if (_isRefreshing) {
    // Queue callers while refresh is in-flight
    return new Promise((resolve) => _refreshQueue.push(resolve));
  }

  _isRefreshing = true;
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      clearTokens();
      _refreshQueue.forEach((cb) => cb(null));
      _refreshQueue = [];
      return null;
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    _refreshQueue.forEach((cb) => cb(data.access_token));
    _refreshQueue = [];
    return data.access_token;
  } catch {
    clearTokens();
    _refreshQueue.forEach((cb) => cb(null));
    _refreshQueue = [];
    return null;
  } finally {
    _isRefreshing = false;
  }
}

// ── Core fetch wrapper with auto-refresh ──────────────────────────────────────

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  let res = await fetch(`${API_URL}${path}`, { ...init, headers });

  // Auto-refresh on 401
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_URL}${path}`, { ...init, headers });
    }
  }

  return res;
}

// ── Public helpers ────────────────────────────────────────────────────────────

export async function apiGet<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiDelete(path: string): Promise<void> {
  const res = await apiFetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Streaming chat ────────────────────────────────────────────────────────────

/**
 * Stream a chat message via SSE. Returns an AbortController so the caller can cancel.
 */
export function streamChat(
  message: string,
  conversationId: string | null,
  onChunk: (chunk: string) => void,
  onDone: (conversationId: string | null) => void,
  onError: (err: Error) => void
): AbortController {
  const controller = new AbortController();
  const token = getToken();

  const doFetch = async (authToken: string | null) => {
    try {
      const res = await fetch(`${API_URL}/chat/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ message, conversation_id: conversationId }),
        signal: controller.signal,
      });

      if (res.status === 401) {
        // Try refreshing then retry once
        const newToken = await refreshAccessToken();
        if (newToken) {
          doFetch(newToken);
          return;
        } else {
          onError(new Error("Session expired. Please log in again."));
          return;
        }
      }

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let foundConversationId: string | null = conversationId;
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? ""; // keep incomplete last line in buffer

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);

          // Decode JSON-encoded text chunks; tool events are passed through raw
          let decoded: string;
          if (
            data.startsWith("__tool_event__:") ||
            data.startsWith("__conversation_id__:") ||
            data === "[DONE]"
          ) {
            decoded = data;
          } else {
            try {
              // Backend JSON-encodes text chunks to preserve \n and special chars
              decoded = JSON.parse(data);
            } catch {
              decoded = data; // fallback: use raw if not valid JSON
            }
          }

          if (decoded === "[DONE]") {
            onDone(foundConversationId);
            return;
          }
          if (decoded.startsWith("__conversation_id__:")) {
            foundConversationId = decoded.slice("__conversation_id__:".length);
            continue;
          }
          onChunk(decoded);
        }
      }
      onDone(foundConversationId);
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        onError(err as Error);
      }
    }
  };

  doFetch(token);
  return controller;
}

export { API_URL, setTokens, clearTokens };
