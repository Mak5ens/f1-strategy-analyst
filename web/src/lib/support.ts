/**
 * The QG ticket widget (MAK-124): a « Signaler » button that files a bug, a request or a question as a task of the
 * mak5ens lore, with the page, the browser, recent errors, failed requests, the steps and a screenshot.
 *
 * Its key is public by nature (it ends up in the page, like a Sentry DSN) and QG only takes it from the origins
 * declared for it. It is read when a page is served, so one image runs anywhere: without `QG_SUPPORT_KEY`, no button.
 */
export interface SupportConfig {
  /** The QG instance that serves /support.js and receives the tickets. */
  url: string;
  key: string;
  environment: string;
  version: string | null;
}

export function supportConfig(env: Record<string, string | undefined> = process.env): SupportConfig | null {
  if (!env.QG_SUPPORT_KEY) return null;
  return {
    url: (env.QG_URL || "https://qg.labbtech.fr").replace(/\/$/, ""),
    key: env.QG_SUPPORT_KEY,
    environment: env.APP_ENV || "production",
    version: env.APP_VERSION || null,
  };
}
