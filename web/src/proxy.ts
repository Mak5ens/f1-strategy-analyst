import { type NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE, mustRenew, REFRESH_COOKIE, setCookieValue, withCookie } from "@/lib/session";

/**
 * Renews the SSO's token before a page renders (LAB-192), when it is missing or about to expire and a refresh
 * token is there: one call to LabbTech Auth's `/auth/refresh` with the visitor's cookies. Its new cookies go to the
 * browser, and into this request's own `Cookie` header, so the page calls the API with the new token. When the
 * SSO refuses, its deletion of the cookies goes to the browser and the page renders signed out; when it does not
 * answer, nothing is deleted. Without AUTH_API_URL there is no SSO: nothing to renew.
 */
export async function proxy(request: NextRequest) {
  const authApi = process.env.AUTH_API_URL;
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!authApi || !mustRenew(token, refresh)) return NextResponse.next();

  let renewed: Response;
  try {
    renewed = await fetch(`${authApi.replace(/\/$/, "")}/auth/refresh`, {
      method: "POST",
      headers: { cookie: request.headers.get("cookie") ?? "" },
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    return NextResponse.next();
  }
  const cookies = renewed.headers.getSetCookie();
  const headers = new Headers(request.headers);
  headers.set(
    "cookie",
    withCookie(headers.get("cookie"), AUTH_COOKIE, renewed.ok ? (setCookieValue(cookies, AUTH_COOKIE) ?? "") : ""),
  );
  const response = NextResponse.next({ request: { headers } });
  for (const cookie of cookies) response.headers.append("set-cookie", cookie);
  return response;
}

export const config = {
  // Pages and server actions; not the static files, the images, nor the sign-in and sign-out routes.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon|connexion|deconnexion).*)"],
};
