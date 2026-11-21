import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Terravanta — Farm intelligence",
  description: "Veterinary-first farm management and crop–livestock traceability for Kenyan mixed farms.",
  metadataBase: new URL((process.env.NEXT_PUBLIC_SITE_URL || "https://terravanta-five.vercel.app").replace(/\/$/, "")),
  robots: { index: false, follow: true },
  verification: process.env.GOOGLE_SITE_VERIFICATION ? { google: process.env.GOOGLE_SITE_VERIFICATION } : undefined,
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
