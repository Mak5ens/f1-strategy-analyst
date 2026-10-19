import Link from "next/link";
import type { ReactNode } from "react";

/** A section's title, wide and upper case after the red slash, with an optional link on the right. */
export function SectionTitle({ children, href, link }: { children: ReactNode; href?: string; link?: string }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <h2 className="display flex items-center gap-3 text-2xl sm:text-3xl">
        <span className="slash" aria-hidden />
        {children}
      </h2>
      {href && link && (
        <Link href={href} className="font-semibold text-sm hover:text-primary-text">
          {link} →
        </Link>
      )}
    </div>
  );
}
