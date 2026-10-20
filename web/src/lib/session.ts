/**
 * The visitor's session with LabbTech Auth, the SSO of every LabbTech app (LAB-192), as plain functions.
 *
 * The SSO sets two httpOnly cookies on its whole domain: `auth_token`, a JWT valid about 15 minutes, and
 * `refresh_token`, which renews it for 30 days. This site never checks the token itself: the API does, on every
 * call, against the SSO's public keys. The site only reads when it expires, to renew it in time (`proxy.ts`), and
 * forwards it to the API.
 */

export const AUTH_COOKIE = "auth_token";
export const REFRESH_COOKIE = "refresh_token";

/** The token is renewed when it has less than this left: a page's calls to the API must not outlive it. */
export const RENEW_BEFORE_S = 60;

/** When a JWT expires, in seconds since the epoch, read without checking its signature; null if unreadable. */
export function expiry(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const json = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return typeof json.exp === "number" ? json.exp : null;
  } catch {
    return null;
  }
}

/** Whether a request must renew its token first: none, unreadable, or about to expire, with a refresh token. */
export function mustRenew(token: string | undefined, refresh: string | undefined, now = Date.now() / 1000): boolean {
  if (!refresh) return false;
  const exp = token ? expiry(token) : null;
  return exp === null || exp - now < RENEW_BEFORE_S;
}

/** A path of this site to come back to, or the home page: never another site's address. */
export function safePath(path: string | null | undefined): string {
  return path?.startsWith("/") && !path.startsWith("//") && !path.startsWith("/\\") ? path : "/";
}

/** The SSO's sign-in page, which sends the visitor back to `path` on this site once signed in. */
export function signInUrl(authAppUrl: string, appUrl: string, path: string | null | undefined): string {
  const back = new URL(safePath(path), appUrl).toString();
  return `${authAppUrl.replace(/\/$/, "")}/login?redirect=${encodeURIComponent(back)}`;
}

/** The value of a cookie in `Set-Cookie` headers, or null when they do not set it. */
export function setCookieValue(headers: string[], name: string): string | null {
  for (const header of headers) {
    const [pair] = header.split(";");
    const at = pair?.indexOf("=") ?? -1;
    if (pair && at > 0 && pair.slice(0, at).trim() === name) return decodeURIComponent(pair.slice(at + 1).trim());
  }
  return null;
}

/** A `Cookie` header with `name` set to `value` (removed when empty), the others kept. */
export function withCookie(header: string | null, name: string, value: string): string {
  const kept = (header ?? "")
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part && !part.startsWith(`${name}=`));
  return [...kept, ...(value ? [`${name}=${value}`] : [])].join("; ");
}
