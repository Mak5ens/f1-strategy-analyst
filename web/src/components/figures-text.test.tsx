import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FiguresText } from "./figures-text";

afterEach(cleanup);

describe("FiguresText", () => {
  it("sets each number apart, the text unchanged", () => {
    const { container } = render(<FiguresText text="Leclerc a perdu 24.8 s au tour 33, soit 0,0192 s par tour." />);
    expect([...container.querySelectorAll("span")].map((span) => span.textContent)).toEqual(["24.8", "33", "0,0192"]);
    expect(container.textContent).toBe("Leclerc a perdu 24.8 s au tour 33, soit 0,0192 s par tour.");
  });
});
