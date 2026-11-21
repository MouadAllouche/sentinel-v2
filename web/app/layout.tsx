import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { Providers } from "@/components/layout/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel",
  description: "Read-only security monitoring for one Linux server",
};

// A nonce-based CSP requires every page to be rendered per request: static
// output is generated at build time, when no request headers (and therefore no
// nonce) exist. `connection()` opts the whole tree out of prerendering.
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection();
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
