"use client";

import { cn } from "cn";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

const links = [
  { href: "/", label: t.nav.home },
  { href: "/grand-prix", label: t.nav.races },
  { href: "/en-attente", label: t.nav.waiting },
  { href: "/debriefs", label: t.nav.published },
  { href: "/reglement", label: t.nav.rules },
];

function active(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** The bar on every page: the app's name, and the sections, the current one underlined in red. */
export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b bg-band/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-col px-4 sm:h-16 sm:flex-row sm:items-center sm:gap-8">
        <Link href="/" className="flex h-14 shrink-0 items-center gap-2 sm:h-auto" aria-label={t.metadata.title}>
          <span className="slash text-2xl" aria-hidden />
          <span className="display whitespace-nowrap text-base sm:text-lg">
            {t.brand.name} <span className="text-primary">{t.brand.tagline}</span>
          </span>
        </Link>
        <nav className="-mx-3 -mb-px flex h-11 items-stretch overflow-x-auto sm:mx-0 sm:h-full">
          {links.map((link) => (
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
      </div>
    </header>
  );
}
