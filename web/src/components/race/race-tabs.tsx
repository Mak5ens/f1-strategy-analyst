"use client";

import { Tabs } from "radix-ui";
import type { ReactNode } from "react";

export type RaceTab = { id: string; label: string; content: ReactNode };

/** The sections of a race's page, one at a time, the current one underlined in red as the header's. */
export function RaceTabs({ tabs, initial }: { tabs: RaceTab[]; initial?: string }) {
  return (
    <Tabs.Root defaultValue={tabs.some((tab) => tab.id === initial) ? initial : tabs[0]?.id}>
      <Tabs.List className="-mx-4 mb-8 flex overflow-x-auto border-b px-4 sm:mx-0 sm:px-0">
        {tabs.map((tab) => (
          <Tabs.Trigger
            key={tab.id}
            value={tab.id}
            className="-mb-px shrink-0 border-transparent border-b-2 px-4 py-3 font-semibold text-muted-foreground text-sm uppercase tracking-wide transition-colors hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground"
          >
            {tab.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {tabs.map((tab) => (
        <Tabs.Content key={tab.id} value={tab.id} className="outline-none">
          {tab.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
