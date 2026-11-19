import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, client } from "@/lib/api/client";

const unsafe = ["POST", "PUT", "PATCH", "DELETE"];

function requestHeaders(fetchMock: ReturnType<typeof vi.fn>): Headers {
  const request = fetchMock.mock.calls[0]?.[0] as Request;
  return request.headers;
}

function call(method: string): Promise<unknown> {
  if (method === "POST") return client.POST("/api/engine/run", {} as never);
  if (method === "PUT") return client.PUT("/api/allowlist/{identifier}", {
    params: { path: { identifier: 1 } },
    body: {},
  } as never);
  if (method === "PATCH") return client.PATCH("/api/users/{identifier}", {
    params: { path: { identifier: 1 } },
    body: {},
  } as never);
  return client.DELETE("/api/allowlist/{identifier}", {
    params: { path: { identifier: 1 } },
  } as never);
}

describe("typed API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "sentinel_csrf=; path=/; max-age=0";
  });

  it("does not send a CSRF header on safe methods", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await client.GET("/api/health");
    expect(requestHeaders(fetchMock).get("X-CSRF-Token")).toBeNull();
  });

  it.each(unsafe)("sends the CSRF cookie on %s", async (method) => {
    document.cookie = "sentinel_csrf=abc123; path=/";
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    const promise = call(method);
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    expect(requestHeaders(fetchMock).get("X-CSRF-Token")).toBe("abc123");
  });

  it("maps an error envelope to ApiError with details", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "validation_error",
          message: "invalid rule",
          details: [{ path: "tiers[0].count", message: "too small" }],
        },
      }),
      { status: 422, headers: { "content-type": "application/json" } },
    );
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    await expect(client.POST("/api/rules", { body: {} })).rejects.toBeInstanceOf(ApiError);
    try {
      await client.POST("/api/rules", { body: {} });
    } catch (error) {
      expect(error).toMatchObject({ code: "validation_error", status: 422 });
      expect((error as ApiError).details?.[0]?.path).toBe("tiers[0].count");
    }
  });

  it("signals unauthorized on a 401 response", async () => {
    const listener = vi.fn();
    window.addEventListener("sentinel:unauthorized", listener);
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(client.GET("/api/health")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener("sentinel:unauthorized", listener);
  });

  it("never stores tokens in localStorage", () => {
    expect(window.localStorage.length).toBe(0);
  });
});
