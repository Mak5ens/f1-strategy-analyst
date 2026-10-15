import { fr, type Messages } from "@/messages/fr";

/** The interface's language: French only for now. A second one adds a dictionary and a way to choose. */
export const locale = "fr";

const dictionaries: Record<typeof locale, Messages> = { fr };

export function getMessages(): Messages {
  return dictionaries[locale];
}
