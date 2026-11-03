import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { ActorProvider, ActorSelector } from "@/lib/actor";

export const metadata: Metadata = {
  title: "Certificate Admin Console",
  description: "Tenant admin console for course certificates",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <ActorProvider>
          <header className="border-b bg-white">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
              <Link href="/" className="font-semibold">
                Certificate Admin Console
              </Link>
              <ActorSelector />
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </ActorProvider>
      </body>
    </html>
  );
}
