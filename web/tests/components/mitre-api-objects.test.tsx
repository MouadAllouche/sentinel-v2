import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MitreBadge } from "@/components/badges/ExplanationBadges";
import { fixture, type MitreTag } from "../fixtures";

const tag = (fixture<{ items: Array<{ mitre: MitreTag[] }> }>("incidents").items[0]?.mitre[0])!;

describe("MITRE tags from the real API", () => {
  it("renders an API object as text and a link, never as a React child", () => {
    expect(tag).toMatchObject({ id: expect.any(String), url: expect.stringContaining("attack.mitre.org") });
    const { container } = render(<MitreBadge technique={tag} />);
    expect(container.textContent).toContain(tag.id);
    expect(screen.getByRole("link")).toHaveAttribute("href", tag.url);
    expect(container.textContent).toContain("indicative");
    expect(container.querySelector("object")).toBeNull();
  });

  it("keeps working with a legacy string id", () => {
    render(<MitreBadge technique="T1110" />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://attack.mitre.org/techniques/T1110/",
    );
  });
});
