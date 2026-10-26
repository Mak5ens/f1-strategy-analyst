import { describe, expect, it } from "vitest";
import { supportConfig } from "./support";

describe("supportConfig", () => {
  it("is off without a key", () => {
    expect(supportConfig({ QG_URL: "https://qg.example" })).toBeNull();
  });

  it("defaults to the QG of LabbTech, in production", () => {
    expect(supportConfig({ QG_SUPPORT_KEY: "qgt_k" })).toEqual({
      url: "https://qg.labbtech.fr",
      key: "qgt_k",
      environment: "production",
      version: null,
    });
  });

  it("reads the instance, environment and version", () => {
    expect(
      supportConfig({
        QG_SUPPORT_KEY: "qgt_k",
        QG_URL: "http://localhost:8000/",
        APP_ENV: "development",
        APP_VERSION: "1.2.0",
      }),
    ).toEqual({ url: "http://localhost:8000", key: "qgt_k", environment: "development", version: "1.2.0" });
  });
});
