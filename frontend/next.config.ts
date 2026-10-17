import { networkInterfaces } from "node:os";
import type { NextConfig } from "next";

// The browser calls /api/* on this same server, and Next forwards it to FastAPI.
// That works from any address (localhost, 127.0.0.1, a phone on the LAN) with no CORS setup.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

// This computer's LAN addresses (they change with the Wi-Fi network), so the "Network:" URL
// that `next dev` prints works, including from a phone on the same Wi-Fi.
const lanAddresses = Object.values(networkInterfaces())
  .flat()
  .filter((a) => a && a.family === "IPv4" && !a.internal)
  .map((a) => a!.address);

const nextConfig: NextConfig = {
  // The server builds into a side folder and swaps it in (deploy/deploy.sh), so a failed build never takes the site down.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  cacheComponents: true,
  partialPrefetching: true,
  // Dev only: hostnames besides localhost that may load the dev server's scripts. *.trycloudflare.com is the
  // free HTTPS tunnel (`cloudflared tunnel --url http://localhost:3000`) used to test GPS and camera on a phone.
  allowedDevOrigins: ["127.0.0.1", ...lanAddresses, "*.trycloudflare.com"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_PROXY_TARGET}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
