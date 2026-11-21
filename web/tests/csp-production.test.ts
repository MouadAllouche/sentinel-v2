// @vitest-environment node
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const PORT = 3123;
const BASE = `http://127.0.0.1:${PORT}`;
const webRoot = path.resolve(__dirname, "..");

let server: ChildProcess | undefined;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForServer(): Promise<void> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${BASE}/login`, { redirect: "manual" });
      if (response.status > 0) return;
    } catch {
      // not ready yet
    }
    await sleep(500);
  }
  throw new Error("production Next server did not start");
}

beforeAll(async () => {
  server = spawn("npm", ["run", "start", "--", "--port", String(PORT)], {
    cwd: webRoot,
    env: { ...process.env, SENTINEL_SESSION_KEY: "csp-test-session-key-0123456789abcdef" },
    stdio: "ignore",
    detached: true,
  });
  await waitForServer();
}, 60_000);

afterAll(() => {
  if (server?.pid) {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      // already stopped
    }
  }
});

function nonceFrom(csp: string | null): string {
  const match = /'nonce-([^']+)'/.exec(csp ?? "");
  if (!match) throw new Error(`CSP header has no nonce: ${csp}`);
  return match[1]!;
}

async function fetchPage(url: string, cookie?: string) {
  return fetch(`${BASE}${url}`, {
    redirect: "manual",
    headers: cookie ? { Cookie: cookie } : {},
  });
}

describe("production CSP nonce", () => {
  it("puts a nonce matching the CSP header on every /login script", async () => {
    const response = await fetchPage("/login");
    expect(response.status).toBe(200);
    const csp = response.headers.get("content-security-policy");
    const scriptSrc = /script-src[^;]*/.exec(csp ?? "")?.[0] ?? "";
    expect(scriptSrc).toContain("'strict-dynamic'");
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    const nonce = nonceFrom(csp);
    const html = await response.text();
    const tags = [...html.matchAll(/<script\b[^>]*>/g)].map((match) => match[0]);
    expect(tags.length).toBeGreaterThan(0);
    for (const tag of tags) {
      expect(tag, `script without matching nonce: ${tag}`).toContain(`nonce="${nonce}"`);
    }
  });

  it("does not prerender /login or authenticated pages", async () => {
    const login = await fetchPage("/login");
    expect(login.headers.get("x-nextjs-prerender")).toBeNull();
    expect(login.headers.get("x-nextjs-cache")).toBeNull();

    const app = await fetchPage("/events", "sentinel_session=csp-test-cookie");
    expect(app.status).toBe(200);
    expect(app.headers.get("x-nextjs-prerender")).toBeNull();
    const nonce = nonceFrom(app.headers.get("content-security-policy"));
    const html = await app.text();
    const tags = [...html.matchAll(/<script\b[^>]*>/g)].map((match) => match[0]);
    expect(tags.length).toBeGreaterThan(0);
    for (const tag of tags) {
      expect(tag).toContain(`nonce="${nonce}"`);
    }
  });
});
