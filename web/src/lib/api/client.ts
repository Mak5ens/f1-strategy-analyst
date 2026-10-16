import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Info = components["schemas"]["Info"];
export type Debrief = components["schemas"]["Debrief"];
export type DebriefSummary = components["schemas"]["DebriefSummary"];
export type Subject = components["schemas"]["Subject"];
export type Status = DebriefSummary["status"];
export type Stop = NonNullable<DebriefSummary["waiting"]>;

/**
 * The API's client, typed by the schema generated from FastAPI's OpenAPI (`just web-gen-client`): a route or a field
 * the API no longer has fails the type check, not the page.
 *
 * Called by server components and server actions: API_URL is where the Next.js server reaches the API (the `api`
 * service in compose.yaml), never sent to the browser.
 */
export function apiClient(baseUrl: string = process.env.API_URL ?? "http://localhost:8000") {
  return createClient<paths>({ baseUrl });
}

type Client = ReturnType<typeof apiClient>;

/** The service's identity, or null when the API does not answer. */
export async function fetchInfo(client: Client = apiClient()): Promise<Info | null> {
  try {
    const { data } = await client.GET("/info", { cache: "no-store", signal: AbortSignal.timeout(3000) });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The requests, the latest first, all or those of one status; null when the API does not answer. */
export async function fetchDebriefs(status?: Status, client: Client = apiClient()): Promise<DebriefSummary[] | null> {
  try {
    const { data } = await client.GET("/debriefs", {
      params: { query: { status } },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}
