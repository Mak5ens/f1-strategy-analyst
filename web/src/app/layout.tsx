import type { Metadata } from "next";
import type { ReactNode } from "react";
import { getMessages, locale } from "@/lib/i18n";
import "./globals.css";

const messages = getMessages();

export const metadata: Metadata = {
  title: messages.metadata.title,
  description: messages.metadata.description,
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang={locale}>
      <body className="min-h-dvh font-sans">{children}</body>
    </html>
  );
}
