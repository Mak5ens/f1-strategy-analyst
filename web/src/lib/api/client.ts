import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Info = components["schemas"]["Info"];
export type Debrief = components["schemas"]["Debrief"];
export type DebriefSummary = components["schemas"]["DebriefSummary"];
export type Subject = components["schemas"]["Subject"];
export type Status = DebriefSummary["status"];
export type Stop = NonNullable<DebriefSummary["waiting"]>;
export type Driver = components["schemas"]["Driver"];
export type Analysis = components["schemas"]["Analysis"];
export type Point = components["schemas"]["ShownPoint"];
export type Decision = components["schemas"]["Decision"];
export type Fact = components["schemas"]["Fact"];
export type Source = components["schemas"]["Source"];
export type JournalEntry = components["schemas"]["JournalEntry"];
export type QuestionReply = components["schemas"]["QuestionReply"];
export type Race = components["schemas"]["Race"];
export type RaceLaps = components["schemas"]["RaceLaps"];
export type FactChart = components["schemas"]["FactChart"];
export type RaceSummary = components["schemas"]["RaceSummary"];
export type FreeAnswer = components["schemas"]["FreeAnswer"];
export type Choice = components["schemas"]["Choice"];

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

/** The races the home page puts forward, the last one raced first; null when the API does not answer. */
export async function fetchFeatured(client: Client = apiClient()): Promise<RaceSummary[] | null> {
  try {
    const { data } = await client.GET("/races/featured", { signal: AbortSignal.timeout(10000) });
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
/** A race lap by lap, for its charts; "missing" when it has no laps, null when the API cannot be reached. */
export async function fetchRaceLaps(
  season: number,
  round: number,
  client: Client = apiClient(),
): Promise<RaceLaps | "missing" | null> {
  try {
    const { data, response } = await client.GET("/races/{season}/{round_number}/laps", {
      params: { path: { season, round_number: round } },
      signal: AbortSignal.timeout(15000),
    });
    if (response.status === 404) return "missing";
    return data ?? null;
  } catch {
    return null;
  }
}

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

/** A request and what its stop needs; null when it does not exist or the API does not answer. */
export async function fetchDebrief(id: string, client: Client = apiClient()): Promise<Debrief | null> {
  try {
    const { data } = await client.GET("/debriefs/{debrief_id}", {
      params: { path: { debrief_id: id } },
      signal: AbortSignal.timeout(10000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The journal of the reviews, the latest first: all, of one debrief, or of some actions. */
export async function fetchJournal(
  query: { debrief?: string; action?: Decision["action"][] } = {},
  client: Client = apiClient(),
): Promise<JournalEntry[] | null> {
  try {
    const { data } = await client.GET("/decisions", { params: { query }, signal: AbortSignal.timeout(10000) });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The questions asked on a debrief and their replies, the first first; null when the API does not answer. */
export async function fetchQuestions(id: string, client: Client = apiClient()): Promise<QuestionReply[] | null> {
  try {
    const { data } = await client.GET("/debriefs/{debrief_id}/questions", {
      params: { path: { debrief_id: id } },
      signal: AbortSignal.timeout(10000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}

/** A free question of the home page and its answer; null when it does not exist or the API does not answer. */
export async function fetchFreeQuestion(id: number, client: Client = apiClient()): Promise<FreeAnswer | null> {
  try {
    const { data } = await client.GET("/questions/{question_id}", {
      params: { path: { question_id: id } },
      signal: AbortSignal.timeout(5000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}

/** The latest free questions first; null when the API does not answer. */
export async function fetchFreeQuestions(limit = 6, client: Client = apiClient()): Promise<FreeAnswer[] | null> {
  try {
    const { data } = await client.GET("/questions", {
      params: { query: { limit } },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return data ?? null;
  } catch {
    return null;
  }
}
