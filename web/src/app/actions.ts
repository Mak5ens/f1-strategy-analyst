"use server";

import { redirect } from "next/navigation";
import { apiClient } from "@/lib/api/client";

export type StartState = { error: boolean };

/** Start a debrief, then open it: the agent has run to its first stop, the plan or a question. */
export async function startDebrief(_: StartState, form: FormData): Promise<StartState> {
  const request = String(form.get("request") ?? "").trim();
  if (request.length < 3) return { error: true };
  const { data } = await apiClient()
    .POST("/debriefs", { body: { request }, signal: AbortSignal.timeout(120_000) })
    .catch(() => ({ data: undefined }));
  if (!data) return { error: true };
  redirect(`/debriefs/${data.id}`);
}
