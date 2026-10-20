import { type NextRequest, NextResponse } from "next/server";

/**
 * Sign out of LabbTech Auth, on every LabbTech app at once (LAB-192): its `/auth/logout` revokes the refresh token
 * and deletes the shared cookies, whose deletion goes to the browser. A form posts here, never a link: a GET could
 * be triggered by another site.
 */
export async function POST(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/", request.url), 303);
  const authApi = process.env.AUTH_API_URL;
  if (!authApi) return response;
  const out = await fetch(`${authApi.replace(/\/$/, "")}/auth/logout`, {
    method: "POST",
    headers: { cookie: request.headers.get("cookie") ?? "" },
    signal: AbortSignal.timeout(3000),
  }).catch(() => null);
  for (const cookie of out?.headers.getSetCookie() ?? []) response.headers.append("set-cookie", cookie);
  return response;
}
