"use server";

import { redirect } from "next/navigation";
import { apiClient, type Decision } from "@/lib/api/client";

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
