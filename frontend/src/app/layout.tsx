import type { Metadata } from "next";
import { Sora, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sora = Sora({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-sora",
  display: "swap",
});
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.VERCEL_URL
      ? `https://${process.env.VERCEL_URL}`
      : "http://localhost:3000"
  ),
  title: "XPrediction — The prediction layer for the real world",
  description:
    "Deployable, signal-driven prediction infrastructure. Aggregate live markets, wire real-world signals, and white-label the whole layer under your brand.",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  manifest: "/site.webmanifest",
  openGraph: {
    title: "XPrediction — The prediction layer for the real world",
    description:
      "Deployable, signal-driven prediction infrastructure — aggregate, launch and white-label markets for anything.",
    type: "website",
    images: [{ url: "/web-app-manifest-512x512.png", width: 512, height: 512, alt: "XPrediction" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "XPrediction — The prediction layer for the real world",
    description: "Deployable, signal-driven prediction infrastructure.",
    images: ["/web-app-manifest-512x512.png"],
  },
};

export const viewport = {
  themeColor: "#0f131a",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${sora.variable} ${inter.variable} ${jetbrains.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
