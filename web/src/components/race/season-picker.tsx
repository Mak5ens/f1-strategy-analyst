import { cn } from "cn";
import Link from "next/link";

/** The seasons of the data as pills, the current one in red. */
export function SeasonPicker({
  seasons,
  current,
  href,
}: {
  seasons: number[];
  current: number;
  href: (season: number) => string;
}) {
  return (
    <nav className="flex gap-2">
      {seasons.map((season) => (
        <Link
          key={season}
          href={href(season)}
          scroll={false}
          aria-current={season === current ? "page" : undefined}
          className={cn(
            "figures rounded-full border px-4 py-1.5 font-semibold text-sm transition-colors hover:border-foreground/40",
            "aria-[current=page]:border-primary aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground",
          )}
        >
          {season}
        </Link>
      ))}
    </nav>
  );
}
