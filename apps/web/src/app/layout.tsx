import type { Metadata, Viewport } from "next";

import { BuildRefresh } from "@/components/build-refresh";

import "./globals.css";

export const viewport: Viewport = {
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#4F46E5" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0F1A" },
  ],
};

export const metadata: Metadata = {
  title: {
    default: "SiftEntry",
    template: "%s | SiftEntry",
  },
  description: "Invoices in. Entries ready.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "SiftEntry",
  },
  icons: {
    apple: "/icons/apple-touch-icon.png",
    icon: [
      {
        url: "/brand/siftentry-favicon-32.png",
        sizes: "32x32",
        type: "image/png",
      },
      {
        url: "/brand/siftentry-favicon-64.png",
        sizes: "64x64",
        type: "image/png",
      },
    ],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <BuildRefresh />
        {children}
      </body>
    </html>
  );
}
