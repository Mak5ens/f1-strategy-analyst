import type { NextConfig } from "next";

const config: NextConfig = {
  // A server of its own in .next/standalone, with only the files it needs: what the Dockerfile copies.
  output: "standalone",
  poweredByHeader: false,
  // `next dev` would write AGENTS.md and CLAUDE.md in web/: the repo's CLAUDE.md points to the same docs.
  agentRules: false,
};

export default config;
