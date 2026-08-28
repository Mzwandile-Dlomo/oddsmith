import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { SlipStoreProvider } from "@/store/slip-store";
import { MobileNav, Sidebar } from "@/components/shell/Sidebar";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "Oddsmith — Soccer Bet Builder",
  description: "Build, track, and settle soccer bets",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={geist.variable}>
      <body className="min-h-screen bg-[#FAFAFA] font-sans antialiased">
        <QueryProvider>
          <SlipStoreProvider>
            <Sidebar />
            <div className="lg:pl-60">
              <div className="sticky top-0 z-30 border-b border-[#E5E7EB] bg-white/95 pt-3 backdrop-blur-md lg:hidden">
                <div className="flex items-center gap-2.5 px-4 pb-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#6C47FF]">
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" aria-hidden="true" fill="none">
                      <circle cx="12" cy="12" r="5" fill="white" />
                    </svg>
                  </div>
                  <span className="text-[15px] font-semibold tracking-tight text-[#111827]">
                    Oddsmith
                  </span>
                </div>
                <MobileNav />
              </div>
              <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
            </div>
          </SlipStoreProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
