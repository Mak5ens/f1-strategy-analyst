/**
 * Every text of the interface, in French. A component reads its texts here (`getMessages()`), never inline: a
 * translation is another file of the same shape (`Messages`), chosen by `locale` in src/lib/i18n.ts.
 */
export const fr = {
  metadata: {
    title: "Analyste stratégie F1",
    description:
      "Débriefs stratégiques de Grands Prix, sourcés par les données de chronométrage et le règlement de la FIA, validés par un analyste.",
  },
  home: {
    title: "Analyste stratégie F1",
    lead: "Un agent rédige le débrief stratégique d'un Grand Prix à partir des données de chronométrage et du règlement de la FIA. Un analyste valide chaque point avant publication.",
    soon: "Les demandes de débrief, les validations et les débriefs publiés arrivent ici.",
  },
  apiStatus: {
    title: "État du service",
    up: "Disponible",
    down: "Injoignable",
    version: (version: string) => `Version ${version}`,
    unreachable: "L'API ne répond pas. Lancez-la avec `just up`.",
  },
} as const;

export type Messages = typeof fr;
