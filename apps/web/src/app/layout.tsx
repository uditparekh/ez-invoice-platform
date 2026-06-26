import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SiftEntry",
    template: "%s | SiftEntry",
  },
  description: "Invoices in. Entries ready.",
  icons: {
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
      <body>{children}</body>
    </html>
  );
}
