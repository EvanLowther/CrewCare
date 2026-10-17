import { NextResponse } from "next/server";
import { auth0 } from "./lib/auth0";

// Next 16's proxy (formerly middleware): Auth0's /auth/login, /auth/callback, /auth/logout, /auth/access-token
// routes, and keeping sessions rolling. Pages stay public; the API decides what each viewer sees.
export async function proxy(request: Request) {
  if (!auth0) return NextResponse.next();
  return await auth0.middleware(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|api/).*)"],
};
