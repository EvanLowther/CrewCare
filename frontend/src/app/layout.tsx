import type { Metadata, Viewport } from "next";
import { Big_Shoulders, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { MeProvider } from "@/components/MeProvider";
import { TopNav } from "@/components/TopNav";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

// Condensed display face for headlines and the big scores.
const bigShoulders = Big_Shoulders({
  variable: "--font-big-shoulders",
  subsets: ["latin"],
  weight: ["600", "800"],
});

export const metadata: Metadata = {
  title: "Crew Care",
  description: "The forecast your crew actually needs: a 0-10 hazard score for every job site, now and for the next 24 hours",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#06080c",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} ${bigShoulders.variable} h-full antialiased`}>
      <body className="min-h-full bg-page text-ink">
        <MeProvider>
          <TopNav />
          {children}
        </MeProvider>
      </body>
    </html>
  );
}
