import { describe, expect, it } from "vitest";
import { apiClient, fetchInfo } from "./client";

function answering(response: () => Response) {
  const client = apiClient("http://api.test");
  client.use({ onRequest: () => response() });
  return client;
}

describe("fetchInfo", () => {
  it("reads the service's identity", async () => {
    const client = answering(() => Response.json({ name: "f1-strategy-analyst", version: "0.5.0" }));
    expect(await fetchInfo(client)).toEqual({ name: "f1-strategy-analyst", version: "0.5.0" });
  });

  it("gives null on an error status", async () => {
    expect(await fetchInfo(answering(() => new Response("", { status: 503 })))).toBeNull();
  });

  it("gives null when the API cannot be reached", async () => {
    const client = apiClient("http://127.0.0.1:9");
    expect(await fetchInfo(client)).toBeNull();
  });
});
