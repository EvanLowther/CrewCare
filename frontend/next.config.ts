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
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Dev only: hostnames besides localhost that may load the dev server's scripts.
  allowedDevOrigins: ["127.0.0.1", ...lanAddresses],
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
