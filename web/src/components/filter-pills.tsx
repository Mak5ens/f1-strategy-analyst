import { cn } from "cn";
import Link from "next/link";

export type Pill = { label: string; href: string; active: boolean };

/** Filters as links, the active one in red: a filtered page has its own URL. */
export function FilterPills({ pills }: { pills: Pill[] }) {
  return (
    <nav className="flex flex-wrap gap-2">
      {pills.map((pill) => (
        <Link
          key={pill.href}
          href={pill.href}
          scroll={false}
          aria-current={pill.active ? "page" : undefined}
          className={cn(
            "rounded-full border px-4 py-1.5 font-semibold text-sm transition-colors hover:border-foreground/40",
            "aria-[current=page]:border-primary aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground",
          )}
        >
          {pill.label}
        </Link>
      ))}
    </nav>
  );
}
