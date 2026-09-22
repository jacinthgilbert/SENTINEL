import "leaflet/dist/leaflet.css";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import Shell from "./Shell";

export const metadata: Metadata = {
  title: "The Sentinel",
  description: "Flood early-warning and response · Visakhapatnam",
  manifest: "/manifest.json",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { themeColor: "#14110D" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><Shell>{children}</Shell></body>
    </html>
  );
}
