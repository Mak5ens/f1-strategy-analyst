import Link from "next/link";
import type { ReactNode } from "react";
import { fetchSession, isAnalyst } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

/**
 * What only an analyst does (LAB-192): ask, answer a stop. Anyone else sees why, and how to sign in; the API refuses
 * them anyway, this only spares them a form that would fail.
 */
export async function AnalystOnly({ children, back }: { children: ReactNode; back: string }) {
  const session = await fetchSession();
  if (isAnalyst(session)) return children;
  return (
    <div className="rounded-xl border bg-surface p-5 text-sm">
      <p className="text-muted-foreground">{session.viewer ? t.auth.notAnalyst : t.auth.askLead}</p>
      {session.viewer ? null : <SignInLink back={back} className="mt-3 inline-block" />}
    </div>
  );
}

/** The page of a section only analysts read, when the visitor is not one. */
export async function ReservedPage({ back }: { back: string }) {
  const session = await fetchSession();
  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="display text-3xl">{t.auth.reservedTitle}</h1>
      <p className="mt-4 text-muted-foreground">{session.viewer ? t.auth.notAnalyst : t.auth.reservedLead}</p>
      {session.viewer ? null : <SignInLink back={back} className="mt-6 inline-block" />}
    </main>
  );
}

export function SignInLink({ back, className }: { back: string; className?: string }) {
  return (
    <Link
      href={`/connexion?retour=${encodeURIComponent(back)}`}
      prefetch={false}
      className={`font-medium text-primary-text underline-offset-4 hover:underline ${className ?? ""}`}
    >
      {t.auth.signIn}
    </Link>
  );
}
