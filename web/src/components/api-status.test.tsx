import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiStatus } from "./api-status";

afterEach(cleanup);

describe("ApiStatus", () => {
  it("shows the version when the API answers", () => {
    render(<ApiStatus info={{ name: "f1-strategy-analyst", version: "0.5.0" }} />);
    expect(screen.getByText("Disponible")).toBeDefined();
    expect(screen.getByText("Version 0.5.0")).toBeDefined();
  });

  it("says how to start the API when it does not answer", () => {
    render(<ApiStatus info={null} />);
    expect(screen.getByText("Injoignable")).toBeDefined();
    expect(screen.getByText(/just up/)).toBeDefined();
  });
});
