import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "@/components/layout/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel",
  description: "Read-only security monitoring for one Linux server",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
