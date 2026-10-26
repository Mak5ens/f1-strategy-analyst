import type { Metadata } from "next";
import { Archivo, Inter } from "next/font/google";
import type { ReactNode } from "react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { SupportWidget } from "@/components/support-widget";
import { fetchSession } from "@/lib/api/client";
import { getMessages, locale } from "@/lib/i18n";
import { supportConfig } from "@/lib/support";
import "./globals.css";

// Archivo with its width axis, for the wide titles; Inter for the text. Both under the SIL Open Font License, served
// from the app's own origin by next/font.
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

const messages = getMessages();

export const metadata: Metadata = {
  title: messages.metadata.title,
  description: messages.metadata.description,
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const session = await fetchSession();
  const support = supportConfig();
  return (
    <html lang={locale} className={`${archivo.variable} ${inter.variable}`}>
      <body className="flex min-h-dvh flex-col">
        <SiteHeader session={session} />
        <div className="flex-1">{children}</div>
        <SiteFooter />
        {support && <SupportWidget config={support} viewer={session.viewer} />}
      </body>
    </html>
  );
}
