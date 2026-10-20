import { type NextRequest, NextResponse } from "next/server";
import { signInUrl } from "@/lib/session";

/** Sign in on LabbTech Auth, which sends the visitor back to `?retour=` on this site (LAB-192). */
export function GET(request: NextRequest) {
  const authApp = process.env.AUTH_APP_URL;
  if (!authApp) return NextResponse.redirect(new URL("/", request.url));
  const appUrl = process.env.APP_URL ?? request.nextUrl.origin;
  return NextResponse.redirect(signInUrl(authApp, appUrl, request.nextUrl.searchParams.get("retour")));
}
