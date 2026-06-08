import { describe, expect, it } from "vitest";
import { legacyCompetitorRedirectHref } from "./SourcesMappingFeature";

describe("SourcesMappingFeature navigation", () => {
  it("preserves product context when redirecting legacy competitor tabs", () => {
    expect(legacyCompetitorRedirectHref("cat phone", "product_70")).toBe(
      "/sources?tab=sources&category=cat+phone&product=product_70",
    );
  });

  it("keeps the competitor redirect usable without category or product", () => {
    expect(legacyCompetitorRedirectHref("", "")).toBe("/sources?tab=sources");
  });
});
