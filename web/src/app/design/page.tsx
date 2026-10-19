import type { Metadata } from "next";
import { FilterPills } from "@/components/filter-pills";
import { MotionDemo } from "@/components/motion-demo";
import { SectionTitle } from "@/components/section-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getMessages } from "@/lib/i18n";

const t = getMessages().design;

export const metadata: Metadata = {
  title: `${t.title} · ${getMessages().metadata.title}`,
  robots: { index: false, follow: false },
};

const swatch = "flex flex-col gap-2 rounded-xl border bg-surface p-3 text-xs";

/**
 * The design system's reference (LAB-188): principles, tokens and base components, all from globals.css. Internal:
 * not in the navigation, not indexed. docs/design.md says why each choice was made.
 */
export default function DesignPage() {
  const tile = (name: string, className: string) => (
    <div key={name} className={swatch}>
      <span className={`h-12 rounded-md border ${className}`} />
      <code className="text-muted-foreground">--{name}</code>
    </div>
  );
  return (
    <main className="enter mx-auto flex max-w-6xl flex-col gap-12 px-4 py-12">
      <header className="flex flex-col gap-3">
        <p className="flex items-center gap-2 font-semibold text-primary-text text-sm uppercase tracking-wider">
          <span className="slash" aria-hidden />
          LAB-188
        </p>
        <h1 className="display text-4xl sm:text-6xl">{t.title}</h1>
        <p className="max-w-3xl text-lg text-muted-foreground">{t.lead}</p>
      </header>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.principles}</SectionTitle>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {t.principlesList.map(([title, text], index) => (
            <li key={title} className="flex flex-col gap-2 rounded-xl border bg-surface p-4">
              <span className="figures font-semibold text-primary-text text-xs">0{index + 1}</span>
              <span className="font-semibold">{title}</span>
              <span className="text-muted-foreground text-sm">{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.surfaces}</SectionTitle>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tile("background", "bg-background")}
          {tile("band", "bg-band")}
          {tile("surface", "bg-surface")}
          {tile("surface-raised", "bg-surface-raised")}
          {tile("primary", "bg-primary")}
          {tile("hover", "bg-hover")}
          {tile("border", "bg-border")}
          {tile("ring", "bg-ring")}
        </div>
        <SectionTitle>{t.text}</SectionTitle>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["foreground", "text-foreground"],
            ["muted-foreground", "text-muted-foreground"],
            ["primary-text", "text-primary-text"],
            ["success", "text-success"],
            ["warning", "text-warning"],
            ["destructive", "text-destructive"],
            ["fastest", "text-fastest"],
          ].map(([name, className]) => (
            <div key={name} className={swatch}>
              <span className={`display text-2xl ${className}`}>1:21.3</span>
              <code className="text-muted-foreground">--{name}</code>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.data}</SectionTitle>
        <p className="max-w-3xl text-muted-foreground text-sm">{t.dataLead}</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tile("soft", "bg-soft")}
          {tile("medium", "bg-medium")}
          {tile("hard", "bg-hard")}
          {tile("intermediate", "bg-intermediate")}
          {tile("wet", "bg-wet")}
          {tile("fastest", "bg-fastest")}
          {tile("neutralized", "bg-neutralized")}
          {tile("red-flag", "bg-red-flag")}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.typography}</SectionTitle>
        <p className="display text-5xl">{t.display}</p>
        <p className="max-w-2xl">{t.body}</p>
        <p className="figures display text-3xl">
          1:20.901 · +0.248 · P12 <span className="text-muted-foreground text-sm normal-case">{t.figures}</span>
        </p>
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.components}</SectionTitle>
        <div className="flex flex-wrap items-center gap-3">
          <Button>{t.primary}</Button>
          <Button variant="outline">{t.secondary}</Button>
          <Button variant="link">{t.link}</Button>
        </div>
        <FilterPills pills={t.pills.map((label, index) => ({ label, href: `#${index}`, active: index === 0 }))} />
        <div className="flex flex-wrap gap-2">
          <Badge>{t.badges.live}</Badge>
          <Badge variant="secondary">{t.badges.review}</Badge>
          <Badge variant="destructive">{t.badges.error}</Badge>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle>{t.motion}</SectionTitle>
        <p className="max-w-3xl text-muted-foreground text-sm">{t.motionLead}</p>
        <MotionDemo label={t.replay} />
      </section>
    </main>
  );
}
