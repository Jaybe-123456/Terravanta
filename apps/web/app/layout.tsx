import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Terravanta — Farm intelligence",
  description: "Veterinary-first farm management and crop–livestock traceability for Kenyan mixed farms.",
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
