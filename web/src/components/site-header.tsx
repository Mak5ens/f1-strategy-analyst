"use client";

import { cn } from "cn";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Session } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

const links = [
  { href: "/", label: t.nav.home },
  { href: "/grand-prix", label: t.nav.races },
  { href: "/saison", label: t.nav.season },
  { href: "/duel", label: t.nav.duel },
  { href: "/en-attente", label: t.nav.waiting, analyst: true },
  { href: "/debriefs", label: t.nav.published },
  { href: "/journal", label: t.nav.journal, analyst: true },
];

function active(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/**
 * The bar on every page: the app's name, the sections, the current one underlined in red, and the account. The
 * sections only analysts read are shown to analysts (LAB-192); without SSO, there is no account to show.
 */
export function SiteHeader({ session }: { session: Session }) {
  const pathname = usePathname();
  const analyst = session.open || session.viewer?.analyst === true;
  return (
    <header className="sticky top-0 z-40 border-b bg-band/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-col px-4 sm:h-16 sm:flex-row sm:items-center sm:gap-8">
        <div className="flex h-14 items-center justify-between gap-4 sm:h-auto">
          <Link href="/" className="flex shrink-0 items-center gap-2" aria-label={t.metadata.title}>
            <span className="slash text-2xl" aria-hidden />
            <span className="display whitespace-nowrap text-base sm:text-lg">
              {t.brand.name} <span className="text-primary-text">{t.brand.tagline}</span>
            </span>
          </Link>
          <Account session={session} here={pathname} className="flex sm:hidden" />
        </div>
        <nav className="-mx-3 -mb-px flex h-11 items-stretch overflow-x-auto sm:mx-0 sm:h-full">
          {links
            .filter((link) => analyst || !link.analyst)
            .map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active(pathname, link.href) ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center border-b-2 border-transparent px-3 font-medium text-muted-foreground text-sm transition-colors hover:text-foreground",
                  "aria-[current=page]:border-primary aria-[current=page]:text-foreground",
                )}
              >
                {link.label}
              </Link>
            ))}
        </nav>
        <Account session={session} here={pathname} className="ml-auto hidden sm:flex" />
      </div>
    </header>
  );
}

/** The signed-in account and its sign-out, or the sign-in link; nothing on an API without SSO. */
function Account({ session, here, className }: { session: Session; here: string; className?: string }) {
  if (session.open) return null;
  const viewer = session.viewer;
  if (!viewer) {
    return (
      <a
        href={`/connexion?retour=${encodeURIComponent(here)}`}
        className={cn("shrink-0 items-center font-medium text-sm hover:text-primary-text", className)}
      >
        {t.auth.signIn}
      </a>
    );
  }
  return (
    <div className={cn("shrink-0 items-center gap-3 text-sm", className)}>
      <span className="flex flex-col items-end leading-tight">
        <span className="max-w-40 truncate font-medium">{viewer.name}</span>
        <span className="text-muted-foreground text-xs">{viewer.analyst ? t.auth.analyst : t.auth.reader}</span>
      </span>
      <form action="/deconnexion" method="post">
        <button type="submit" className="text-muted-foreground hover:text-foreground">
          {t.auth.signOut}
        </button>
      </form>
    </div>
  );
}
