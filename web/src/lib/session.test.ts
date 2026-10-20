import { describe, expect, it } from "vitest";
import { expiry, mustRenew, safePath, setCookieValue, signInUrl, withCookie } from "./session";

const jwt = (payload: object) => `h.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.s`;

describe("session", () => {
  it("reads when a token expires, without its signature", () => {
    expect(expiry(jwt({ exp: 1000, sub: "a" }))).toBe(1000);
    expect(expiry("garbage")).toBeNull();
    expect(expiry(jwt({ sub: "a" }))).toBeNull();
  });

  it("renews a token about to expire, missing or unreadable, only with a refresh token", () => {
    expect(mustRenew(jwt({ exp: 1000 }), "r", 900)).toBe(false);
    expect(mustRenew(jwt({ exp: 1000 }), "r", 950)).toBe(true);
    expect(mustRenew(undefined, "r", 0)).toBe(true);
    expect(mustRenew("garbage", "r", 0)).toBe(true);
    expect(mustRenew(undefined, undefined, 0)).toBe(false);
  });

  it("sends the visitor back to this site only", () => {
    expect(safePath("/grand-prix/2025/16?onglet=course")).toBe("/grand-prix/2025/16?onglet=course");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "", null]) {
      expect(safePath(bad)).toBe("/");
    }
    expect(signInUrl("http://localhost:3002/", "http://localhost:3001", "/en-attente")).toBe(
      "http://localhost:3002/login?redirect=http%3A%2F%2Flocalhost%3A3001%2Fen-attente",
    );
  });

  it("reads and replaces cookies", () => {
    const set = ["refresh_token=r2; Path=/; HttpOnly", "auth_token=t%202; Path=/; HttpOnly"];
    expect(setCookieValue(set, "auth_token")).toBe("t 2");
    expect(setCookieValue(set, "other")).toBeNull();
    expect(withCookie("a=1; auth_token=old; b=2", "auth_token", "new")).toBe("a=1; b=2; auth_token=new");
    expect(withCookie("auth_token=old", "auth_token", "")).toBe("");
  });
});
