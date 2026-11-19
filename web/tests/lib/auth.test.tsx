import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RequireRole, validateNextPath } from "@/lib/auth";

describe("auth helpers", () => {
  it("rejects open-redirect next parameters", () => {
    expect(validateNextPath("/events")).toBe("/events");
    expect(validateNextPath("https://evil.example/x")).toBe("/");
    expect(validateNextPath("//evil.example")).toBe("/");
    expect(validateNextPath("javascript:alert(1)")).toBe("/");
  });

  it("RequireRole renders protected content only for the right role", () => {
    const { rerender } = render(
      <RequireRole requiredRole="admin" roleOfUser="viewer">
        <button type="button">Admin only</button>
      </RequireRole>,
    );
    expect(screen.queryByText("Admin only")).toBeNull();

    rerender(
      <RequireRole requiredRole="admin" roleOfUser="admin">
        <button type="button">Admin only</button>
      </RequireRole>,
    );
    expect(screen.getByText("Admin only")).toBeInTheDocument();
  });
});
