import type { ReactNode } from "react";

/** The black band a list page opens with: an eyebrow-less title, a line of explanation, and its filters. */
export function PageHeader({ title, lead, children }: { title: string; lead: string; children?: ReactNode }) {
  return (
    <section className="border-b bg-band">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-8 sm:pt-16">
        <h1 className="display flex items-center gap-3 text-4xl sm:text-5xl">
          <span className="slash" aria-hidden />
          {title}
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">{lead}</p>
        {children && <div className="mt-2 flex flex-col gap-3">{children}</div>}
      </div>
    </section>
  );
}
