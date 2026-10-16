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
  brand: { name: "Analyste", tagline: "stratégie" },
  nav: {
    home: "Accueil",
    waiting: "En attente",
    published: "Débriefs",
    rules: "Règlement",
  },
  home: {
    eyebrow: "Débrief stratégique",
    title: "Chaque arrêt, chaque écart, expliqué.",
    lead: "Demandez le débrief d'un Grand Prix, pour la course, une écurie ou un pilote. L'agent calcule tout à partir des données de chronométrage, cite le règlement, puis vous soumet chaque point avant publication.",
    placeholder: "Débrief stratégique du GP d'Italie 2025 pour Ferrari",
    submit: "Lancer le débrief",
    submitting: "L'agent prépare le plan…",
    examples: "Exemples",
    exampleRequests: [
      "Débrief du GP de São Paulo 2024 pour Verstappen",
      "Débrief stratégique du GP de Monaco 2025",
      "Débrief du GP de Grande-Bretagne 2025 pour McLaren",
    ],
    waitingTitle: "En attente de vous",
    waitingEmpty: "Aucune demande n'attend de décision.",
    publishedTitle: "Derniers débriefs",
    publishedEmpty: "Aucun débrief publié pour l'instant.",
    seeAll: "Tout voir",
    error: "La demande n'a pas pu être lancée. Réessayez dans un instant.",
  },
  stops: {
    clarification: { label: "Précision", action: "Choisir la course" },
    plan: { label: "Plan à valider", action: "Valider le plan" },
    review: { label: "Revue", action: "Relire les points" },
  },
  subject: {
    unresolved: "Course à préciser",
    race: "Toute la course",
    round: (round: number) => `Manche ${round}`,
  },
  table: {
    grandPrix: "Grand Prix",
    season: "Saison",
    subject: "Débrief pour",
    published: "Publié",
  },
  apiStatus: {
    up: "API disponible",
    down: "API injoignable",
    version: (version: string) => `version ${version}`,
    unreachable: "L'API ne répond pas. Lancez-la avec `just up`.",
  },
  footer: {
    disclaimer:
      "Projet non officiel, sans lien avec la Formula 1 ni la FIA. Données publiques de chronométrage, usage non commercial.",
  },
};

export type Messages = typeof fr;
