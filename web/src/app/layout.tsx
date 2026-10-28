import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { SlipStoreProvider } from "@/store/slip-store";
import { AppShell } from "@/components/shell/Sidebar";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "Oddsmith — Soccer Bet Builder",
  description: "Build, track, and settle soccer bets",
};

export const viewport: Viewport = {
  themeColor: "#FFFFFF",
  // The fixed bottom tab bar needs the real viewport height on iOS, and pinch
  // zoom must stay available for accessibility.
  viewportFit: "cover",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={geist.variable}>
      <body className="min-h-screen bg-canvas font-sans antialiased">
        <QueryProvider>
          <SlipStoreProvider>
            <AppShell>{children}</AppShell>
          </SlipStoreProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
