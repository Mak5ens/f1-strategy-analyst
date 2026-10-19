"use server";

import { redirect } from "next/navigation";
import { apiClient, type Decision, type Simulation } from "@/lib/api/client";

export type StartState = { error: boolean };

/**
 * Start a debrief, then open it: the agent has run to its first stop, the plan or a question. A form on a race's
 * page sends the race (`season`, `round`) and `question`: the agent never asks which race, and answers first.
 */
export async function startDebrief(_: StartState, form: FormData): Promise<StartState> {
  const request = String(form.get("request") ?? "").trim();
  if (request.length < 3) return { error: true };
  const season = Number(form.get("season")) || null;
  const round = Number(form.get("round")) || null;
  const question = form.get("question") === "1";
  const { data } = await apiClient()
    .POST("/debriefs", { body: { request, season, round, question }, signal: AbortSignal.timeout(120_000) })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${data.id}`);
}

export type AnswerState = { error: boolean };

// The agent runs inside the call until its next stop: up to a minute from the plan to the review.
const AGENT_TIMEOUT = 180_000;

/**
 * A free question of the home page (LAB-206): the API routes it. A debrief opens its request; any other answer,
 * or what the analyst must choose, is shown on the home page. A choice comes back with the question: `route`, and
 * the race (`season`, `round`).
 */
export async function askFree(_: AnswerState, form: FormData): Promise<AnswerState> {
  const question = String(form.get("question") ?? "").trim();
  if (question.length < 3) return { error: true };
  const route = (form.get("route") || null) as "rules" | "data" | "debrief" | null;
  const season = Number(form.get("season")) || null;
  const round = Number(form.get("round")) || null;
  const { data } = await apiClient()
    .POST("/questions", { body: { question, route, season, round }, signal: AbortSignal.timeout(AGENT_TIMEOUT) })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  if (data.debrief) redirect(`/debriefs/${data.debrief}`);
  redirect(`/?question=${data.id}#reponse`);
}

/** Choose an option of the agent's question, then show where the request stands. */
export async function answerClarification(id: string, _: AnswerState, form: FormData): Promise<AnswerState> {
  const option = String(form.get("option") ?? "");
  const { data } = await apiClient()
    .POST("/debriefs/{debrief_id}/clarification", {
      params: { path: { debrief_id: id } },
      body: { option },
      signal: AbortSignal.timeout(AGENT_TIMEOUT),
    })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${id}`);
}

/** Run the analyses kept, then show the points to review. */
export async function answerPlan(id: string, _: AnswerState, form: FormData): Promise<AnswerState> {
  const analyses = form.getAll("analysis").map(String);
  const { data } = await apiClient()
    .POST("/debriefs/{debrief_id}/plan", {
      params: { path: { debrief_id: id } },
      body: { analyses },
      signal: AbortSignal.timeout(AGENT_TIMEOUT),
    })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${id}`);
}

/** Send a decision per point; the debrief is published once every point is decided. */
export async function answerReview(id: string, _: AnswerState, form: FormData): Promise<AnswerState> {
  let decisions: Decision[];
  try {
    decisions = JSON.parse(String(form.get("decisions") ?? "[]"));
  } catch {
    return { error: true };
  }
  const { data } = await apiClient()
    .POST("/debriefs/{debrief_id}/review", {
      params: { path: { debrief_id: id } },
      body: { decisions },
      signal: AbortSignal.timeout(AGENT_TIMEOUT),
    })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${id}`);
}

/** Ask a question on a published debrief; its reply, shown or withheld, is added to the thread. (A redirect to the
 * same page with only a hash would scroll without rendering it again.) */
export async function askQuestion(id: string, _: AnswerState, form: FormData): Promise<AnswerState> {
  const question = String(form.get("question") ?? "").trim();
  if (question.length < 3) return { error: true };
  const { data } = await apiClient()
    .POST("/debriefs/{debrief_id}/questions", {
      params: { path: { debrief_id: id } },
      body: { question },
      signal: AbortSignal.timeout(AGENT_TIMEOUT),
    })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${id}`);
}

export type SimulationState = { result: Simulation | null; error: string | null };

/**
 * Another strategy for a driver (LAB-213, LAB-214), asked again at every change of the simulator: the projection, or why
 * the model cannot price it (the API's 422 says it).
 */
export async function simulate(
  season: number,
  round: number,
  driver: string,
  stops: number[] | null,
  rival: string | null,
  compounds: (string | null)[] | null = null,
): Promise<SimulationState> {
  const { data, error } = await apiClient()
    .GET("/races/{season}/{round_number}/simulation", {
      params: {
        path: { season, round_number: round },
        query: {
          driver,
          stops: stops ?? undefined,
          rival: rival ?? undefined,
          // An empty entry keeps the compound raced on that stint.
          compounds: compounds?.map((compound) => compound ?? ""),
        },
      },
      signal: AbortSignal.timeout(15_000),
    })
    .catch(() => ({ data: undefined, error: undefined }));
  if (data) return { result: data, error: null };
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return { result: null, error: typeof detail === "string" ? detail : "unreachable" };
}
