import { describe, expect, it } from "vitest";
import { legacyCompetitorWorkspaceHref } from "./legacyRedirects";

describe("legacy app redirects", () => {
  it("routes competitor links with product context to canonical source mapping", () => {
    expect(legacyCompetitorWorkspaceHref("?category=cat-phone&product=product_70")).toBe(
      "/sources?tab=sources&category=cat-phone&product=product_70",
    );
  });

  it("routes global competitor links to data-source settings", () => {
    expect(legacyCompetitorWorkspaceHref("provider=restore")).toBe(
      "/connectors/status?provider=restore&tab=competitors",
    );
  });
});
