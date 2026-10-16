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
    races: "Courses",
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
  calendar: {
    eyebrow: "Calendrier",
    title: (season: number) => `Saison ${season}`,
    lead: "Choisissez une course : son résultat, sa stratégie et ses débriefs sont sur sa page.",
    sprint: "Sprint",
    winner: "Vainqueur",
    toCome: "Résultats à venir",
    empty: "Aucune course dans les données pour cette saison. Chargez-la avec `just ingest`.",
    unreachable: "Le calendrier n'a pas pu être chargé : l'API ne répond pas.",
  },
  race: {
    round: (round: number, season: number) => `Manche ${round} · ${season}`,
    sprint: "Week-end sprint",
    figures: {
      winner: "Vainqueur",
      fastestLap: "Meilleur tour",
      laps: "Tours",
      neutralizations: "Neutralisations",
      weather: "Air / piste",
      rain: "Pluie",
      dry: "Sec",
    },
    tabs: { result: "Résultat", grid: "Grille", strategy: "Stratégie", standings: "Classements" },
    result: {
      position: "Pos.",
      driver: "Pilote",
      team: "Écurie",
      laps: "Tours",
      time: "Temps / écart",
      bestLap: "Meilleur tour",
      points: "Pts",
      lapsBehind: (laps: number) => (laps === 1 ? "+1 tour" : `+${laps} tours`),
      fastest: "Meilleur tour en course",
      // The data's letters for a driver not classified, as French timing sheets write them.
      positions: { R: "AB", D: "DSQ", W: "NP", N: "NC", E: "EX", F: "NQ" } as Record<string, string>,
      statuses: {
        Finished: "Arrivé",
        Lapped: "Doublé",
        Retired: "Abandon",
        "Did not start": "Non partant",
        Disqualified: "Disqualifié",
        Withdrew: "Forfait",
        "Not classified": "Non classé",
      } as Record<string, string>,
    },
    grid: {
      start: "Départ",
      finish: "Arrivée",
      change: "Places",
      pitLane: "Stands",
      lead: "Places gagnées ou perdues entre la grille et l'arrivée.",
    },
    strategy: {
      lead: "Les relais de chaque pilote, tour par tour. Les bandes jaunes marquent la voiture de sécurité ou le VSC, les rouges un drapeau rouge.",
      lap: "Tour",
      stops: "Arrêts",
      stop: "Arrêt",
      pitLane: "Voie des stands",
      stationary: "Immobile",
      lost: "Temps perdu",
      neutralizedStop: "sous neutralisation",
      used: "pneus déjà utilisés",
      compounds: {
        SOFT: "Tendre",
        MEDIUM: "Medium",
        HARD: "Dur",
        INTERMEDIATE: "Intermédiaire",
        WET: "Pluie",
      } as Record<string, string>,
      unknown: "Inconnu",
    },
    events: {
      title: "Faits de course",
      none: "Ni voiture de sécurité, ni drapeau rouge, ni pénalité.",
      kinds: {
        safety_car: "Voiture de sécurité",
        virtual_safety_car: "Voiture de sécurité virtuelle",
        red_flag: "Drapeau rouge",
      },
      laps: (start: number, end: number) => (start === end ? `tour ${start}` : `tours ${start} à ${end}`),
      penalty: (seconds: number | null, kind: string) =>
        kind === "time"
          ? `Pénalité de ${seconds} s`
          : kind === "drive_through"
            ? "Drive-through"
            : `Stop and go${seconds ? ` de ${seconds} s` : ""}`,
      penaltyLap: (lap: number) => `annoncée au tour ${lap}`,
    },
    standings: {
      drivers: "Pilotes",
      teams: "Constructeurs",
      after: (round: number) => `Après la manche ${round}`,
      points: "Pts",
      wins: "Victoires",
    },
    debriefs: {
      title: "Débriefs de cette course",
      empty: "Aucun débrief sur cette course pour l'instant.",
      ask: "Une question sur cette course ?",
      askLead:
        "Bientôt ici : posez-la directement, par exemple « pourquoi Hamilton est-il parti en pneus tendres ? ». L'agent prépare un débrief ciblé que vous validez.",
      published: "Publié",
    },
    noResults:
      "Cette course n'a pas encore de résultats dans les données. Revenez après l'arrivée, une fois la manche chargée avec `just ingest`.",
    missing: {
      title: "Course introuvable",
      lead: (round: string, season: string) =>
        `Les données n'ont pas de manche ${round} pour la saison ${season}. Elle n'a pas encore été chargée, ou n'existe pas.`,
      back: "Voir le calendrier",
    },
    unreachable: "Cette course n'a pas pu être chargée : l'API ne répond pas.",
    unavailable: "Données indisponibles pour cette section.",
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
