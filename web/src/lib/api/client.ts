import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Info = components["schemas"]["Info"];
export type Debrief = components["schemas"]["Debrief"];
export type DebriefSummary = components["schemas"]["DebriefSummary"];
export type Subject = components["schemas"]["Subject"];
export type Status = DebriefSummary["status"];
export type Stop = NonNullable<DebriefSummary["waiting"]>;
export type Driver = components["schemas"]["Driver"];
export type Race = components["schemas"]["Race"];
export type RaceSummary = components["schemas"]["RaceSummary"];

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

/** The requests, the latest first, all or those of one status, or of one race; null when the API does not answer. */
export async function fetchDebriefs(
  filter: { status?: Status; season?: number; round?: number } = {},
  client: Client = apiClient(),
): Promise<DebriefSummary[] | null> {
  try {
    const { data } = await client.GET("/debriefs", {
      params: { query: filter },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The seasons in the data, the latest first; null when the API does not answer. */
export async function fetchSeasons(client: Client = apiClient()): Promise<number[] | null> {
  try {
    const { data } = await client.GET("/seasons", { signal: AbortSignal.timeout(5000) });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The calendar of a season (the latest if omitted); null when the API does not answer. */
export async function fetchRaces(season?: number, client: Client = apiClient()): Promise<RaceSummary[] | null> {
  try {
    const { data } = await client.GET("/races", {
      params: { query: { season } },
      signal: AbortSignal.timeout(5000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}

/**
 * The page of a race: the race, "missing" when the data has no such round, or null when the API does not answer.
 * A race with results does not change: Next.js may keep it.
 */
export async function fetchRace(
  season: number,
  round: number,
  client: Client = apiClient(),
): Promise<Race | "missing" | null> {
  try {
    const { data, response } = await client.GET("/races/{season}/{round_number}", {
      params: { path: { season, round_number: round } },
      signal: AbortSignal.timeout(15000),
    });
    if (response.status === 404) return "missing";
    return data ?? null;
  } catch {
    return null;
  }
}
