// Data in transit (T21): the SPA refuses a non-HTTPS API origin outside development.
import { describe, expect, it } from "vitest";
import { apiBaseUrl } from "./api";

describe("API origin must be HTTPS in production builds (T21)", () => {
  it("throws for an http:// API URL in a production build", () => {
    expect(() => apiBaseUrl({ VITE_API_BASE_URL: "http://api.example.com", DEV: false })).toThrow(/https/);
  });

  it("throws when the variable is missing", () => {
    expect(() => apiBaseUrl({ VITE_API_BASE_URL: "", DEV: false })).toThrow(/VITE_API_BASE_URL/);
  });

  it("accepts https:// and strips trailing slashes", () => {
    expect(apiBaseUrl({ VITE_API_BASE_URL: "https://api.example.com/", DEV: false })).toBe("https://api.example.com");
  });

  it("allows a local http API only in development", () => {
    expect(apiBaseUrl({ VITE_API_BASE_URL: "http://localhost:8000", DEV: true })).toBe("http://localhost:8000");
  });
});
