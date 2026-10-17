import { Auth0Client } from "@auth0/nextjs-auth0/server";

// Server-side Auth0 client (docs/AUTH.md). Reads AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, AUTH0_SECRET
// and APP_BASE_URL from the environment. Null on laptops, which use the dev "Sign in as" menu instead.
export const auth0 = process.env.AUTH0_DOMAIN
  ? new Auth0Client({
      authorizationParameters: {
        audience: process.env.AUTH0_AUDIENCE,
        // offline_access gives a refresh token, so crews stay signed in without logging in every day.
        scope: "openid profile email offline_access",
      },
      // Signed in for up to 30 days, as long as the site is used at least once a week.
      session: { rolling: true, inactivityDuration: 7 * 24 * 60 * 60, absoluteDuration: 30 * 24 * 60 * 60 },
    })
  : null;
