import type { MetadataRoute } from "next";

// Lets phones add Crew Care to the home screen. iPhones need that before they allow push notifications.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Crew Care",
    short_name: "Crew Care",
    description: "Hazard scores, alerts and crew reports for every job site",
    start_url: "/",
    display: "standalone",
    background_color: "#06080c",
    theme_color: "#06080c",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
