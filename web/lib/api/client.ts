import createClient from "openapi-fetch";
import type { paths } from "./schema";

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function cookie(name: string): string {
  if (typeof document === "undefined") return "";
  const found = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.slice(name.length + 1)) : "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Array<{ path: string; message: string }>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Same-origin in the browser; an absolute base is required for the Request
// constructor in non-browser test environments (jsdom + Node fetch).
const baseUrl = typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:3000";

// Resolve fetch at call time so tests can stub the global without recreating the client.
const dynamicFetch: typeof globalThis.fetch = (input, init) => globalThis.fetch(input, init);

export const client = createClient<paths>({
  baseUrl,
  credentials: "include",
  fetch: dynamicFetch,
});

client.use({
  async onRequest({ request }) {
    if (unsafeMethods.has(request.method.toUpperCase())) {
      const token = cookie("sentinel_csrf");
      if (token) request.headers.set("X-CSRF-Token", token);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.ok) return response;
    const clone = response.clone();
    let body: { error?: { code?: string; message?: string; details?: Array<{ path: string; message: string }> } } = {};
    try {
      body = (await clone.json()) as typeof body;
    } catch {
      // non-JSON error; fall back to status text
    }
    const detail = body.error;
    if (response.status === 401 && !window.location.pathname.startsWith("/login")) {
      window.dispatchEvent(new CustomEvent("sentinel:unauthorized"));
    }
    throw new ApiError(
      response.status,
      detail?.code ?? "request_failed",
      detail?.message ?? response.statusText,
      detail?.details,
    );
  },
});

export function csrfToken(): string {
  return cookie("sentinel_csrf");
}
