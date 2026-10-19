import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The design system's two rules (LAB-188, docs/design.md), checked on the files themselves: every text colour reaches
 * WCAG AA on what it sits on, and colours live only in the tokens of globals.css.
 */

const css = readFileSync(join(__dirname, "globals.css"), "utf8");
const token = (name: string): string => {
  const found = css.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`, "i"))?.[1];
  if (!found) throw new Error(`--${name} is not a #rrggbb token`);
  return found;
};

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((at) => {
    const c = Number.parseInt(hex.slice(at, at + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].toSorted((x, y) => y - x);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

const surfaces = ["background", "band", "surface", "surface-raised"];
const texts = ["foreground", "muted-foreground", "primary-text", "destructive", "success", "warning", "fastest"];

describe("design tokens", () => {
  it.each(texts.flatMap((text) => surfaces.map((surface) => [text, surface])))(
    "%s on %s reaches AA",
    (text, surface) => {
      expect(contrast(token(text), token(surface))).toBeGreaterThanOrEqual(4.5);
    },
  );

  it.each([
    ["primary-foreground", "primary"],
    ["band", "destructive"],
    ["on-data", "soft"],
    ["on-data", "wet"],
    ["band", "medium"],
    ["band", "hard"],
    ["band", "intermediate"],
  ])("%s on %s reaches AA", (text, fill) => {
    expect(contrast(token(text), token(fill))).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps colours out of the components: no #rrggbb, rgb() or fixed white and black", () => {
    const files = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
        entry.isDirectory()
          ? files(join(dir, entry.name))
          : /\.tsx$/.test(entry.name) && !/\.test\./.test(entry.name)
            ? [join(dir, entry.name)]
            : [],
      );
    const offending = files(join(__dirname, "..")).filter((file) =>
      /#[0-9a-f]{6}\b|rgba?\(|\b(?:text|bg|border|fill|stroke)-(?:white|black)(?:\/|\b)/i.test(
        readFileSync(file, "utf8"),
      ),
    );
    expect(offending).toEqual([]);
  });
});
