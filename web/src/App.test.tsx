// Focused test for shouldRestoreMobileMenuFocus — the pure decision behind
// App.tsx's mobile-nav focus-restore effect. Kept out of a full App render
// test: App pulls in routing, plugins, theme, and config fetches that would
// make asserting this one transition rule disproportionately heavy.
import { describe, it, expect } from "vitest";
import { shouldRestoreMobileMenuFocus } from "./App";

describe("shouldRestoreMobileMenuFocus", () => {
  it("restores focus on the open -> closed transition when the button is still connected", () => {
    expect(
      shouldRestoreMobileMenuFocus(true, false, { isConnected: true }),
    ).toBe(true);
  });

  it("does nothing while still open", () => {
    expect(
      shouldRestoreMobileMenuFocus(true, true, { isConnected: true }),
    ).toBe(false);
  });

  it("does nothing on the closed -> open transition", () => {
    expect(
      shouldRestoreMobileMenuFocus(false, true, { isConnected: true }),
    ).toBe(false);
  });

  it("does nothing while already closed", () => {
    expect(
      shouldRestoreMobileMenuFocus(false, false, { isConnected: true }),
    ).toBe(false);
  });

  it("skips a button that unmounted while the menu was open", () => {
    expect(
      shouldRestoreMobileMenuFocus(true, false, { isConnected: false }),
    ).toBe(false);
  });

  it("skips a null button ref", () => {
    expect(shouldRestoreMobileMenuFocus(true, false, null)).toBe(false);
  });
});
