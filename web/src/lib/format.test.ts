import { describe, expect, it } from "vitest";
import { formatGap, formatLapTime, formatPoints, formatRaceTime, formatSeconds } from "./format";

describe("timings", () => {
  it("writes lap times and race times as timing screens do", () => {
    expect(formatLapTime(80.901)).toBe("1:20.901");
    expect(formatLapTime(65.5)).toBe("1:05.500");
    expect(formatLapTime(9.25)).toBe("09.250");
    expect(formatRaceTime(4404.325)).toBe("1:13:24.325");
    expect(formatRaceTime(3605)).toBe("1:00:05.000");
    expect(formatGap(19.207)).toBe("+19.207");
    expect(formatGap(62.519)).toBe("+1:02.519");
  });

  it("writes durations and points in French", () => {
    expect(formatSeconds(24.431)).toBe("24,4 s");
    expect(formatPoints(0.5)).toBe("0,5");
    expect(formatPoints(25)).toBe("25");
  });
});
