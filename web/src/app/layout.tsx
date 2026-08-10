import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { SlipStoreProvider } from "@/store/slip-store";

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
            <header className="fixed inset-x-0 top-0 z-40 h-16 border-b border-[#E5E7EB] bg-white/95 backdrop-blur-md">
              <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-6">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#6C47FF]">
                    <svg
                      viewBox="0 0 24 24"
                      className="h-4 w-4"
                      aria-hidden="true"
                      fill="none"
                    >
                      <path
                        d="M12 3C7.03 3 3 7.03 3 12s4.03 9 9 9 9-4.03 9-9-4.03-9-9-9z"
                        fill="white"
                        opacity="0.3"
                      />
                      <circle cx="12" cy="12" r="5" fill="white" />
                      <path
                        d="M9.5 12l1.5 1.5 3.5-3.5"
                        stroke="#6C47FF"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                  <span className="text-[15px] font-semibold tracking-tight text-[#111827]">
                    Oddsmith
                  </span>
                </div>
                <nav className="hidden items-center gap-1 sm:flex">
                  <span className="rounded-md px-3 py-1.5 text-xs font-medium text-[#6B7280]">
                    v0.1 beta
                  </span>
                </nav>
              </div>
            </header>
            <main className="pt-16">{children}</main>
          </SlipStoreProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
