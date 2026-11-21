// @vitest-environment node
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import AppError from "@/app/error";

describe("error boundary", () => {
  it("logs message, stack and digest during render in every build", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const error = Object.assign(new globalThis.Error("boom"), { digest: "abc123" });
    renderToString(createElement(AppError, { error, reset: () => undefined }));
    expect(spy).toHaveBeenCalledTimes(1);
    const logged = spy.mock.calls[0]?.[0] as string;
    expect(logged).toContain("boom");
    expect(logged).toContain("abc123");
    expect(logged).toContain("Error:");
    spy.mockRestore();
  });
});
