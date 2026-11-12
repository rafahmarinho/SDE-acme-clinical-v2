import { describe, expect, it } from "vitest";
import { safeNext } from "./safeNext";

describe("safeNext (T11/T125)", () => {
  it("follows same-origin in-app paths", () => {
    expect(safeNext("/patients/abc?tab=1", "/home")).toBe("/patients/abc?tab=1");
  });

  it.each(["https://evil.test/", "//evil.test", "/\\evil.test", "javascript:alert(1)", "", null, "/login", "/signed-out?x=1", "patients"])(
    "falls back for %s",
    (raw) => {
      expect(safeNext(raw, "/home")).toBe("/home");
    },
  );
});
