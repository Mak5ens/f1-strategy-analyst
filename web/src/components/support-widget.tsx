"use client";

import Script from "next/script";
import { useEffect } from "react";
import type { Session } from "@/lib/api/client";
import type { SupportConfig } from "@/lib/support";

type Reporter = Record<string, unknown> | null;

declare global {
  interface Window {
    QGSupport?: { definirUtilisateur(user: Reporter): void };
  }
}

/** Attaches the signed-in visitor to the tickets, once the widget runs; it throws until it is initialised. */
function attach(user: Reporter) {
  try {
    window.QGSupport?.definirUtilisateur(user);
  } catch {
    // script blocked or not loaded yet: onReady attaches the visitor when it is
  }
}

/** The « Signaler » button of QG (lib/support.ts), told who reports so a ticket can be replayed with that account. */
export function SupportWidget({ config, viewer }: { config: SupportConfig; viewer: Session["viewer"] }) {
  const user: Reporter = viewer ? { id: viewer.id, name: viewer.name, email: viewer.email ?? null } : null;
  const key = JSON.stringify(user);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` is `user` by value; `user` is a new object each render
  useEffect(() => attach(user), [key]);

  return (
    <Script
      src={`${config.url}/support.js`}
      strategy="afterInteractive"
      data-cle={config.key}
      data-app="f1-strategy-analyst"
      data-environnement={config.environment}
      {...(config.version ? { "data-version": config.version } : {})}
      onReady={() => attach(user)}
    />
  );
}
