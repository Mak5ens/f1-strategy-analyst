<!-- markdownlint-disable MD024 -->

# Notation des réponses de stratégie

Note chaque réponse de 1 à 5 sur la ligne « Note », sans regarder les notes du juge (`judge-grades.json`), puis lance `just eval agreement`.

| Note | Quand |
| -- | -- |
| 5 | La cause principale de la référence, avec les faits qui l'appuient, et rien de faux |
| 4 | La cause principale ; les faits sont partiels ou vagues, mais rien n'est faux |
| 3 | La cause est citée, mais pas comme la principale, ou un détail est faux |
| 2 | Une autre cause principale, même si certains faits sont justes |
| 1 | Faux, inventé, ou pas de réponse |

Quand la référence commence par « Prémisse fausse », la correction est la cause principale : une réponse qui accepte la prémisse vaut 1 ; une réponse qui la corrige se note sur le reste comme ci-dessus.

---

## 1/30 · `strategy-2025-r20-HAM-BEA`

**Question :** Pourquoi Lewis Hamilton a-t-il perdu sa place face à Oliver Bearman lors de leurs premiers arrêts aux stands du Grand Prix de Mexico 2025 ?

### Référence

- **Cause principale :** la pénalité de Lewis Hamilton : une pénalité de 10 s pour avoir gagné un avantage en sortant de la piste, purgée à son arrêt du tour 23, où ses mécaniciens ont dû attendre 10 s avant de toucher la voiture
  - Oliver Bearman est ressorti devant avec 7.9 s d'avance seulement, moins que la pénalité.
- **Écarts :** Lewis Hamilton avait 3.6 s d'avance à la fin du tour 22 ; à la fin du tour 25, Oliver Bearman était devant de 7.9 s, et l'est resté au moins 3 tours.
- **Lewis Hamilton :**
  - arrêt au tour 23
  - tendres de 26 tours remplacés par des mediums neufs
  - 3.5 s immobile hors pénalité
  - 34.6 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 10 s pour avoir gagné un avantage en sortant de la piste purgée à cet arrêt
- **Oliver Bearman :**
  - arrêt au tour 24
  - tendres de 27 tours remplacés par des mediums neufs
  - 2.7 s immobile
  - 21.7 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lewis Hamilton a perdu sa place face à Oliver Bearman lors de leurs premiers arrêts aux stands du Grand Prix de Mexico 2025 en raison d'un sous-virement. Hamilton a effectué son arrêt au stand au 23e tour, tandis que Bearman a attendu le tour suivant, au 24e tour. Avant leurs arrêts, Hamilton avait un avantage de 3,6 secondes sur Bearman. Après leurs arrêts, Bearman a pris 7,877 secondes d'avance sur Hamilton, ce qui a entraîné une perte totale de 11,477 secondes pour Hamilton. En conséquence, Hamilton est passé de la 3e à la 14e place, tandis que Bearman est passé de la 4e à la 9e place.

Note (1 à 5) : 2

---

## 2/30 · `strategy-2024-r22-LEC-HAM-s2`

**Question :** Au Grand Prix de Las Vegas 2024, qui de Lewis Hamilton ou de Charles Leclerc est sorti devant après leurs 2es arrêts aux stands, et pourquoi ?

### Référence

- Lewis Hamilton est sorti devant Charles Leclerc.
- **Cause principale :** l'undercut : Lewis Hamilton s'est arrêté le premier, au tour 27, 4 tours avant Charles Leclerc, et a gagné 7.4 s sur le cycle d'arrêts
  - sur ses pneus durs usagés, il a tourné 1.35 s plus vite par tour que Charles Leclerc, resté en piste sur des durs de 22 tours, sur 2 tours comparables
  - et ce malgré un arrêt qui lui a coûté 0.5 s de plus (22.6 s contre 22.1 s).
- **Écarts :** Charles Leclerc avait 0.7 s d'avance à la fin du tour 26 ; à la fin du tour 32, Lewis Hamilton était devant de 6.7 s, et l'est resté au moins 3 tours.
- **Charles Leclerc :**
  - arrêt au tour 31
  - durs de 22 tours remplacés par des durs neufs
  - 2.9 s immobile
  - 22.1 s perdues au total sur les tours d'entrée et de sortie
- **Lewis Hamilton :**
  - arrêt au tour 27
  - durs de 15 tours remplacés par des durs usagés
  - 2.6 s immobile
  - 22.6 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Au Grand Prix de Las Vegas 2024, Lewis Hamilton est sorti devant Charles Leclerc après leurs 2es arrêts aux stands. Hamilton a gagné 7.355 secondes sur Leclerc grâce à un undercut.

Note (1 à 5) :

---

## 3/30 · `strategy-2026-r11-LAW-RUS`

**Question :** Pourquoi George Russell a-t-il perdu sa place face à Liam Lawson lors de leurs premiers arrêts aux stands du Grand Prix de Hongrie 2026 ?

### Référence

- **Prémisse fausse :** George Russell n'a pas perdu sa place face à Liam Lawson, c'est l'inverse : George Russell a pris celle de Liam Lawson.
- **Cause principale :** l'overcut : George Russell est resté en piste 6 tours de plus que Liam Lawson (arrêts aux tours 21 et 27), et a gagné 2.7 s sur le cycle d'arrêts
  - sur des pneus durs neufs, Liam Lawson n'a repris que 0.32 s par tour, pas assez pour compenser
  - et ce malgré un arrêt qui lui a coûté 2.2 s de plus (24.6 s contre 22.4 s).
- **Écarts :** Liam Lawson avait 0.2 s d'avance à la fin du tour 20 ; à la fin du tour 28, George Russell était devant de 2.6 s, et l'est resté au moins 3 tours.
- **Liam Lawson :**
  - arrêt au tour 21
  - mediums de 21 tours remplacés par des durs neufs
  - 22.4 s perdues au total sur les tours d'entrée et de sortie
- **George Russell :**
  - arrêt au tour 27
  - mediums de 27 tours remplacés par des durs neufs
  - 24.6 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> George Russell a perdu sa place face à Liam Lawson lors de leurs premiers arrêts aux stands du Grand Prix de Hongrie 2026 car il a effectué son arrêt au stand plus tard, au 27e tour, alors que Liam Lawson a arrêté au 21e tour. Russell a gagné 2,718 secondes sur Lawson grâce à cette stratégie d'overcut, ce qui lui a permis de passer devant Lawson. Avant l'arrêt, Russell était en 8e position et Lawson en 7e position. Après l'arrêt, Russell a pris la 9e position et Lawson est passé en 10e position.

Note (1 à 5) :

---

## 4/30 · `strategy-2026-r01-LIN-NOR`

**Question :** Pourquoi Lando Norris a-t-il perdu sa place face à Arvid Lindblad lors de leurs premiers arrêts aux stands du Grand Prix d'Australie 2026 ?

### Référence

- **Prémisse fausse :** Lando Norris n'a pas perdu sa place face à Arvid Lindblad, c'est l'inverse : Lando Norris a pris celle d'Arvid Lindblad.
- **Cause principale :** le moment de l'arrêt sous voiture de sécurité virtuelle (VSC) : Lando Norris s'est arrêté dès le tour 11, Arvid Lindblad seulement au tour 18, quand la neutralisation touchait à sa fin et que l'arrêt coûtait plus cher.
- **Écarts :** Arvid Lindblad avait 0.5 s d'avance à la fin du tour 10 ; à la fin du tour 19, Lando Norris était devant de 7.3 s, et l'est resté au moins 3 tours.
- **Arvid Lindblad :**
  - arrêt au tour 18
  - mediums de 18 tours remplacés par des durs neufs
  - 2.4 s immobile
  - sous voiture de sécurité virtuelle (VSC)
- **Lando Norris :**
  - arrêt au tour 11
  - mediums de 11 tours remplacés par des durs neufs
  - sous voiture de sécurité virtuelle (VSC)
- Drapeau jaune au tour 18.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lando Norris a perdu sa place face à Arvid Lindblad lors de leurs premiers arrêts aux stands du Grand Prix d'Australie 2026 en raison d'un sous-coupe (undercut). Norris a effectué son arrêt au stand au 11e tour, tandis que Lindblad a attendu le 18e tour. Avant les arrêts, Norris était à 0,491 seconde devant Lindblad. Après les arrêts, Norris a gagné 7,743 secondes sur Lindblad, ce qui a inversé leur position sur la piste. Norris est passé de la 7e à la 5e place, tandis que Lindblad est resté 6e. La course a été neutralisée pendant cet épisode.

Note (1 à 5) :

---

## 5/30 · `strategy-2025-r17-SAI-RUS`

**Question :** Pourquoi Carlos Sainz a-t-il perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix d'Azerbaïdjan 2025 ?

### Référence

- **Cause principale :** l'overcut : George Russell est resté en piste 12 tours de plus que Carlos Sainz (arrêts aux tours 27 et 39), et a gagné 4.5 s sur le cycle d'arrêts
  - sur ses durs de 39 tours, il a tourné 0.11 s plus vite par tour que Carlos Sainz, pourtant sur des pneus durs neufs, sur 10 tours comparables
  - son arrêt lui a aussi coûté 1.9 s de moins (19.5 s contre 21.4 s).
- **Écarts :** Carlos Sainz avait 2.7 s d'avance à la fin du tour 26 ; à la fin du tour 40, George Russell était devant de 1.8 s, et l'est resté au moins 3 tours.
- **Carlos Sainz :**
  - arrêt au tour 27
  - mediums de 32 tours remplacés par des durs neufs
  - 2.6 s immobile
  - 21.4 s perdues au total sur les tours d'entrée et de sortie
- **George Russell :**
  - arrêt au tour 39
  - durs de 39 tours remplacés par des mediums usagés
  - 2.3 s immobile
  - 19.5 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Carlos Sainz a perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix d'Azerbaïdjan 2025 en raison d'un sous-virage (undercut). George Russell a effectué son arrêt au stand au 39e tour, alors que Carlos Sainz l'avait fait au 27e tour. Avant les arrêts, Sainz avait un avantage de 2,69 secondes sur Russell. Après les arrêts, Russell a pris l'avantage avec un écart de 1,84 secondes, gagnant ainsi 4,53 secondes sur Sainz. Cela a permis à Russell de passer devant Sainz, qui a ainsi perdu une position.

Note (1 à 5) :

---

## 6/30 · `strategy-2025-r15-VER-HAD-held`

**Question :** Pourquoi Max Verstappen a-t-il perdu sa place face à Isack Hadjar lors de leurs premiers arrêts aux stands du Grand Prix des Pays-Bas 2025 ?

### Référence

- **Prémisse fausse :**
  - Max Verstappen n'a pas perdu sa place face à Isack Hadjar : il était devant avant leurs arrêts et l'est resté après. Les deux se sont arrêtés au tour 23 ; Isack Hadjar n'a rien repris
  - il a même perdu 0.1 s sur le cycle
- **Écarts :** Max Verstappen avait 2.4 s d'avance à la fin du tour 22 ; à la fin du tour 24, Max Verstappen était devant de 2.5 s.
- **Max Verstappen :**
  - arrêt au tour 23
  - tendres de 23 tours remplacés par des mediums neufs
  - 3.4 s immobile
  - sous voiture de sécurité
- **Isack Hadjar :**
  - arrêt au tour 23
  - mediums de 23 tours remplacés par des durs neufs
  - 2.8 s immobile
  - sous voiture de sécurité
- Drapeau jaune au tour 23.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 7/30 · `strategy-2026-r03-PIA-RUS-held`

**Question :** Pourquoi Oscar Piastri a-t-il perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix du Japon 2026 ?

### Référence

- **Prémisse fausse :**
  - Oscar Piastri n'a pas perdu sa place face à George Russell : il était devant avant leurs arrêts et l'est resté après. George Russell a tenté l'overcut en restant en piste 3 tours de plus qu'Oscar Piastri
  - mais n'a rien repris
  - il a même perdu 0.4 s sur le cycle
- **Écarts :** Oscar Piastri avait 1.8 s d'avance à la fin du tour 17 ; à la fin du tour 22, Oscar Piastri était devant de 2.3 s.
- **Oscar Piastri :**
  - arrêt au tour 18
  - mediums de 18 tours remplacés par des durs neufs
  - 2.4 s immobile
  - 22.1 s perdues au total sur les tours d'entrée et de sortie
  - ressorti derrière Max Verstappen (1.1 s)
- **George Russell :**
  - arrêt au tour 21
  - mediums de 21 tours remplacés par des durs neufs
  - 3.0 s immobile
  - sous voiture de sécurité
- Drapeau jaune au tour 22.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Oscar Piastri a perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix du Japon 2026 en raison d'un undercut. George Russell a effectué son arrêt un tour après Oscar Piastri (au 21e tour contre le 18e tour pour Piastri), ce qui a permis à Russell de ressortir des stands avec un avantage de temps. L'écart entre les deux pilotes est passé de -1,83 seconde avant les arrêts à -2,276 secondes après les arrêts, ce qui représente une perte de 0,446 seconde pour Piastri. Malgré cela, aucun des deux pilotes n'a dépassé l'autre, et la course a été neutralisée pendant cette période.

Note (1 à 5) :

---

## 8/30 · `strategy-2025-r02-STR-BEA`

**Question :** Pourquoi Lance Stroll a-t-il perdu sa place face à Oliver Bearman lors de leurs premiers arrêts aux stands du Grand Prix de Chine 2025 ?

### Référence

- **Cause principale :** l'undercut : Oliver Bearman s'est arrêté le premier, au tour 26, 10 tours avant Lance Stroll, et a gagné 8.7 s sur le cycle d'arrêts
  - sur ses pneus mediums neufs, il a tourné 0.81 s plus vite par tour que Lance Stroll, resté en piste sur des durs de 36 tours, sur 8 tours comparables
  - et ce malgré un arrêt qui lui a coûté 0.8 s de plus (22.9 s contre 22.0 s).
- **Écarts :** Lance Stroll avait 0.7 s d'avance à la fin du tour 25 ; à la fin du tour 37, Oliver Bearman était devant de 8.0 s, et l'est resté au moins 3 tours.
- **Lance Stroll :**
  - arrêt au tour 36
  - durs de 36 tours remplacés par des mediums usagés
  - 3.2 s immobile
  - 22.0 s perdues au total sur les tours d'entrée et de sortie
- **Oliver Bearman :**
  - arrêt au tour 26
  - durs de 26 tours remplacés par des mediums neufs
  - 2.9 s immobile
  - 22.9 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lance Stroll a perdu sa place face à Oliver Bearman lors de leurs premiers arrêts aux stands du Grand Prix de Chine 2025 car Bearman a réussi un overcut. Stroll a fait son arrêt au stand au 36e tour, alors que Bearman l'a fait au 26e tour. Avant les arrêts, Stroll était devant Bearman avec un écart de 0,651 seconde. Après les arrêts, Bearman a gagné 8,698 secondes sur Stroll, passant devant lui. Stroll est passé de la 7e à la 14e place, tandis que Bearman est passé de la 8e à la 11e place.

Note (1 à 5) :

---

## 9/30 · `strategy-2024-r07-SAI-PIA`

**Question :** Pourquoi Oscar Piastri a-t-il perdu sa place face à Carlos Sainz lors de leurs premiers arrêts aux stands du Grand Prix d'Émilie-Romagne 2024 ?

### Référence

- **Prémisse fausse :** Oscar Piastri n'a pas perdu sa place face à Carlos Sainz, c'est l'inverse : Oscar Piastri a pris celle de Carlos Sainz.
- **Cause principale :** l'undercut : Oscar Piastri s'est arrêté le premier, au tour 23, 4 tours avant Carlos Sainz, et a gagné 5.8 s sur le cycle d'arrêts
  - sur ses pneus durs usagés, il a tourné 1.29 s plus vite par tour que Carlos Sainz, resté en piste sur des mediums de 27 tours, sur 2 tours comparables
  - son arrêt lui a aussi coûté 0.6 s de moins (26.8 s contre 27.4 s)
  - Carlos Sainz est en plus ressorti des stands derrière Sergio Perez, à 1.1 s.
- **Écarts :** Carlos Sainz avait 0.9 s d'avance à la fin du tour 22 ; à la fin du tour 28, Oscar Piastri était devant de 4.9 s, et l'est resté au moins 3 tours.
- **Carlos Sainz :**
  - arrêt au tour 27
  - mediums de 27 tours remplacés par des durs neufs
  - 27.4 s perdues au total sur les tours d'entrée et de sortie
  - ressorti derrière Sergio Perez (1.1 s)
- **Oscar Piastri :**
  - arrêt au tour 23
  - mediums de 23 tours remplacés par des durs usagés
  - 26.8 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 10/30 · `strategy-2026-r14-NOR-ANT`

**Question :** Pourquoi Lando Norris a-t-il perdu sa place face à Kimi Antonelli lors de leurs premiers arrêts aux stands du Grand Prix d'Espagne 2026 ?

### Référence

- **Cause principale :** le moment de l'arrêt sous voiture de sécurité virtuelle (VSC) : Kimi Antonelli s'est arrêté dès le tour 14, Lando Norris seulement au tour 15, quand la neutralisation touchait à sa fin et que l'arrêt coûtait plus cher.
- **Écarts :** Lando Norris avait 6.2 s d'avance à la fin du tour 13 ; à la fin du tour 16, Kimi Antonelli était devant de 15.7 s, et l'est resté au moins 3 tours.
- **Lando Norris :**
  - arrêt au tour 15
  - mediums de 15 tours remplacés par des durs neufs
  - sous voiture de sécurité virtuelle (VSC)
- **Kimi Antonelli :**
  - arrêt au tour 14
  - mediums de 14 tours remplacés par des durs neufs
  - sous voiture de sécurité virtuelle (VSC)
- Drapeau jaune au tour 14.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lando Norris a perdu sa place face à Kimi Antonelli lors de leurs premiers arrêts aux stands du Grand Prix d'Espagne 2026 car il a effectué son arrêt au stand un tour plus tard qu'Antonelli (au 15e tour contre le 14e tour). Avant l'arrêt, Norris était devant Antonelli avec un écart de -6.219 secondes. Après les arrêts, Antonelli a gagné 21.946 secondes sur Norris, ce qui a permis à Antonelli de passer devant Norris. La course a été neutralisée pendant ces arrêts, ce qui a influencé les écarts de temps.

Note (1 à 5) :

---

## 11/30 · `strategy-2024-r06-RUS-TSU`

**Question :** Pourquoi George Russell a-t-il perdu sa place face à Yuki Tsunoda lors de leurs premiers arrêts aux stands du Grand Prix de Miami 2024 ?

### Référence

- **Cause principale :** un arrêt sous voiture de sécurité : Yuki Tsunoda s'est arrêté au tour 28 pendant la neutralisation, quand le peloton roule au ralenti et qu'un arrêt coûte bien moins de temps sur les autres, alors que George Russell s'était déjà arrêté sous drapeau vert, au tour 24.
- **Écarts :** George Russell avait 1.7 s d'avance à la fin du tour 23 ; à la fin du tour 29, Yuki Tsunoda était devant de 5.8 s, et l'est resté au moins 3 tours.
- **George Russell :**
  - arrêt au tour 24
  - mediums de 27 tours remplacés par des durs neufs
  - 18.4 s perdues au total sur les tours d'entrée et de sortie
- **Yuki Tsunoda :**
  - arrêt au tour 28
  - mediums de 28 tours remplacés par des durs neufs
  - sous voiture de sécurité
- Drapeau jaune au tour 28.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> George Russell a perdu sa place face à Yuki Tsunoda lors de leurs premiers arrêts aux stands du Grand Prix de Miami 2024 car Tsunoda a réalisé un "overcut" sur Russell. Tsunoda a effectué son arrêt au stand au 28e tour, alors que Russell l'a fait au 24e tour. Avant les arrêts, l'écart entre eux était de 1,678 seconde en faveur de Russell. Après les arrêts, Tsunoda a gagné 7,471 secondes sur Russell, ce qui lui a permis de passer devant et de gagner deux positions, passant de la 8e à la 7e place, tandis que Russell est passé de la 7e à la 9e place.

Note (1 à 5) :

---

## 12/30 · `strategy-2024-r18-HAM-RUS`

**Question :** Pourquoi Lewis Hamilton a-t-il perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix de Singapour 2024 ?

### Référence

- **Cause principale :** l'overcut : George Russell est resté en piste 10 tours de plus que Lewis Hamilton (arrêts aux tours 17 et 27), et a gagné 6.0 s sur le cycle d'arrêts
  - sur ses mediums de 27 tours, il a tourné 0.40 s plus vite par tour que Lewis Hamilton, pourtant sur des pneus durs neufs, sur 8 tours comparables
  - son arrêt lui a aussi coûté 0.9 s de moins (28.2 s contre 29.1 s).
- **Écarts :** Lewis Hamilton avait 1.9 s d'avance à la fin du tour 16 ; à la fin du tour 28, George Russell était devant de 4.1 s, et l'est resté au moins 3 tours.
- **Lewis Hamilton :**
  - arrêt au tour 17
  - tendres de 19 tours remplacés par des durs neufs
  - 29.1 s perdues au total sur les tours d'entrée et de sortie
- **George Russell :**
  - arrêt au tour 27
  - mediums de 27 tours remplacés par des durs neufs
  - 28.2 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lewis Hamilton a perdu sa place face à George Russell lors de leurs premiers arrêts aux stands du Grand Prix de Singapour 2024 en raison d'un undercut. George Russell a effectué son arrêt au 27e tour, alors que Lewis Hamilton l'avait fait au 17e tour. Avant les arrêts, Hamilton avait un avantage de 1,867 seconde sur Russell. Après les arrêts, Russell a pris un avantage de 4,096 secondes sur Hamilton, ce qui a entraîné une perte nette de 5,963 secondes pour Hamilton. En conséquence, Hamilton est passé de la 3e à la 8e place, tandis que Russell est passé de la 4e à la 7e place, Russell ayant dépassé Hamilton.

Note (1 à 5) :

---

## 13/30 · `strategy-2024-r20-VER-NOR`

**Question :** Pourquoi Max Verstappen a-t-il perdu sa place face à Lando Norris lors de leurs premiers arrêts aux stands du Grand Prix de Mexico 2024 ?

### Référence

- **Cause principale :** la pénalité de Max Verstappen : une pénalité de 10 s pour avoir poussé un autre pilote hors de la piste, purgée à son arrêt du tour 26, où ses mécaniciens ont dû attendre 10 s avant de toucher la voiture
  - Lando Norris est ressorti devant avec 18.6 s d'avance seulement, moins que la pénalité.
- **Écarts :** Max Verstappen avait 0.8 s d'avance à la fin du tour 25 ; à la fin du tour 31, Lando Norris était devant de 18.6 s, et l'est resté au moins 3 tours.
- **Max Verstappen :**
  - arrêt au tour 26
  - mediums de 26 tours remplacés par des durs neufs
  - 4.0 s immobile hors pénalité
  - 42.9 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 10 s pour avoir poussé un autre pilote hors de la piste purgée à cet arrêt
  - une pénalité de 10 s pour avoir gagné un avantage en sortant de la piste purgée à cet arrêt
- **Lando Norris :**
  - arrêt au tour 30
  - mediums de 30 tours remplacés par des durs neufs
  - 2.3 s immobile
  - 22.7 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Max Verstappen a perdu sa place face à Lando Norris lors de leurs premiers arrêts aux stands du Grand Prix de Mexico 2024 en raison d'un écart de temps significatif après son arrêt. Avant son arrêt au stand au 26e tour, Verstappen avait un avantage de 0.777 secondes sur Norris. Après son arrêt, l'écart s'est inversé, avec Norris ayant désormais un avantage de 18.631 secondes sur Verstappen. Cet écart de 19.408 secondes en défaveur de Verstappen explique pourquoi il a perdu sa position face à Norris.

Note (1 à 5) :

---

## 14/30 · `strategy-2024-r09-RIC-STR`

**Question :** Pourquoi Daniel Ricciardo a-t-il perdu sa place face à Lance Stroll lors de leurs premiers arrêts aux stands du Grand Prix du Canada 2024 ?

### Référence

- **Cause principale :** le moment de l'arrêt sous voiture de sécurité : Lance Stroll s'est arrêté dès le tour 25, Daniel Ricciardo 1 tour plus tard, au tour 26
  - resté en piste derrière la voiture de sécurité pendant que le peloton se regroupait, Daniel Ricciardo a perdu les 4.3 s d'avance qu'il avait et est ressorti derrière.
- **Écarts :** Daniel Ricciardo avait 4.3 s d'avance à la fin du tour 24 ; à la fin du tour 27, Lance Stroll était devant de 10.1 s, et l'est resté au moins 3 tours.
- **Daniel Ricciardo :**
  - arrêt au tour 26
  - intermédiaires de 26 tours remplacés par des intermédiaires neufs
  - une pénalité de 5 s pour un faux départ purgée à cet arrêt
  - sous voiture de sécurité
- **Lance Stroll :**
  - arrêt au tour 25
  - intermédiaires de 25 tours remplacés par des intermédiaires neufs
  - sous voiture de sécurité
- Drapeau jaune au tour 25.
- Piste humide, pneus intermédiaires, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 15/30 · `strategy-2025-r12-PIA-NOR-s2`

**Question :** Au Grand Prix de Grande-Bretagne 2025, qui d'Oscar Piastri ou de Lando Norris est sorti devant après leurs 2es arrêts aux stands, et pourquoi ?

### Référence

- Lando Norris est sorti devant Oscar Piastri.
- **Cause principale :** la pénalité d'Oscar Piastri : une pénalité de 10 s pour une infraction sous voiture de sécurité, purgée à son arrêt du tour 43, où ses mécaniciens ont dû attendre 10 s avant de toucher la voiture
  - Lando Norris est ressorti devant avec 4.8 s d'avance seulement, moins que la pénalité.
- **Écarts :** Oscar Piastri avait 1.4 s d'avance à la fin du tour 42 ; à la fin du tour 45, Lando Norris était devant de 4.8 s, et l'est resté au moins 3 tours.
- **Oscar Piastri :**
  - arrêt au tour 43
  - intermédiaires de 32 tours remplacés par des mediums neufs
  - 4.6 s immobile hors pénalité
  - 36.6 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 10 s pour une infraction sous voiture de sécurité purgée à cet arrêt
- **Lando Norris :**
  - arrêt au tour 44
  - intermédiaires de 33 tours remplacés par des mediums neufs
  - 2.4 s immobile
  - 34.8 s perdues au total sur les tours d'entrée et de sortie
- Drapeau jaune aux tours 43 et 44.
- Piste humide, pneus intermédiaires, sans pluie pendant le cycle.

### Réponse du système

> Lando Norris est sorti devant Oscar Piastri après leurs 2es arrêts aux stands. Oscar Piastri a effectué son arrêt au 43e tour, tandis que Lando Norris a effectué le sien au 44e tour. Après leurs arrêts, Lando Norris a gagné 6.128 secondes sur Oscar Piastri, passant ainsi devant lui.

Note (1 à 5) :

---

## 16/30 · `strategy-2025-r09-HAM-RUS-s2`

**Question :** Pourquoi Lewis Hamilton a-t-il perdu sa place face à George Russell lors de leurs 2es arrêts aux stands du Grand Prix d'Espagne 2025 ?

### Référence

- **Cause principale :** l'undercut : George Russell s'est arrêté le premier, au tour 41, 5 tours avant Lewis Hamilton, et a gagné 14.4 s sur le cycle d'arrêts
  - sur ses pneus tendres neufs, il a tourné 2.23 s plus vite par tour que Lewis Hamilton, resté en piste sur des mediums de 30 tours, sur 3 tours comparables
  - son arrêt lui a aussi coûté 5.6 s de moins (20.0 s contre 25.6 s).
- **Écarts :** Lewis Hamilton avait 1.9 s d'avance à la fin du tour 40 ; à la fin du tour 47, George Russell était devant de 12.6 s, et l'est resté au moins 3 tours.
- **Lewis Hamilton :**
  - arrêt au tour 46
  - mediums de 30 tours remplacés par des tendres usagés
  - 4.9 s immobile
  - 25.6 s perdues au total sur les tours d'entrée et de sortie
- **George Russell :**
  - arrêt au tour 41
  - mediums de 21 tours remplacés par des tendres neufs
  - 2.3 s immobile
  - 20.0 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Lewis Hamilton a perdu sa place face à George Russell lors de leurs 2es arrêts aux stands du Grand Prix d'Espagne 2025 car George Russell a réussi un overcut. Avant l'arrêt, Lewis Hamilton était devant George Russell de 1,891 seconde. Après l'arrêt, George Russell a pris 12,551 secondes d'avance sur Lewis Hamilton, ce qui a permis à George Russell de le dépasser et de gagner 2 positions, passant de la 6e à la 5e place, tandis que Lewis Hamilton est passé de la 5e à la 7e place.

Note (1 à 5) :

---

## 17/30 · `strategy-2026-r07-COL-GAS-held`

**Question :** Pourquoi Franco Colapinto a-t-il perdu sa place face à Pierre Gasly lors de leurs premiers arrêts aux stands du Grand Prix de Barcelone 2026 ?

### Référence

- **Prémisse fausse :**
  - Franco Colapinto n'a pas perdu sa place face à Pierre Gasly : il était devant avant leurs arrêts et l'est resté après. Pierre Gasly a tenté l'overcut en restant en piste 2 tours de plus que Franco Colapinto
  - mais n'a rien repris
  - il a même perdu 3.1 s sur le cycle
- **Écarts :** Franco Colapinto avait 0.9 s d'avance à la fin du tour 11 ; à la fin du tour 15, Franco Colapinto était devant de 4.0 s.
- **Franco Colapinto :**
  - arrêt au tour 12
  - tendres de 12 tours remplacés par des durs neufs
  - 3.3 s immobile
  - 23.6 s perdues au total sur les tours d'entrée et de sortie
- **Pierre Gasly :**
  - arrêt au tour 14
  - mediums de 14 tours remplacés par des durs neufs
  - 3.0 s immobile
  - 24.9 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Franco Colapinto a perdu sa place face à Pierre Gasly lors de leurs premiers arrêts aux stands du Grand Prix de Barcelone 2026 en raison d'un sous-virement. Colapinto a effectué son arrêt au stand au 12e tour, tandis que Gasly a attendu le 14e tour. Malgré cela, Colapinto n'a pas réussi à dépasser Gasly, et l'écart entre eux a même augmenté, passant de -0.902 secondes avant les arrêts à -3.996 secondes après les arrêts, ce qui représente une perte de 3.094 secondes. Colapinto était 12e avant les arrêts et est passé à la 14e place après, tandis que Gasly est passé de la 13e à la 15e place.

Note (1 à 5) :

---

## 18/30 · `strategy-2024-r09-NOR-VER`

**Question :** Au Grand Prix du Canada 2024, qui de Max Verstappen ou de Lando Norris est sorti devant après leurs premiers arrêts aux stands, et pourquoi ?

### Référence

- Max Verstappen est sorti devant Lando Norris.
- **Cause principale :** le moment de l'arrêt sous voiture de sécurité : Max Verstappen s'est arrêté dès le tour 25, Lando Norris 1 tour plus tard, au tour 26
  - resté en piste derrière la voiture de sécurité pendant que le peloton se regroupait, Lando Norris a perdu les 7.7 s d'avance qu'il avait et est ressorti derrière.
- **Écarts :** Lando Norris avait 7.7 s d'avance à la fin du tour 24 ; à la fin du tour 27, Max Verstappen était devant de 3.1 s, et l'est resté au moins 3 tours.
- **Lando Norris :**
  - arrêt au tour 26
  - intermédiaires de 26 tours remplacés par des intermédiaires neufs
  - sous voiture de sécurité
- **Max Verstappen :**
  - arrêt au tour 25
  - intermédiaires de 25 tours remplacés par des intermédiaires neufs
  - sous voiture de sécurité
- Drapeau jaune au tour 25.
- Piste humide, pneus intermédiaires, sans pluie pendant le cycle.

### Réponse du système

> Max Verstappen est sorti devant Lando Norris après leurs premiers arrêts aux stands. Lando Norris a effectué son arrêt au 26e tour, tandis que Max Verstappen l'a fait au 25e tour. Après leurs arrêts, Max Verstappen a gagné 10.779 secondes sur Lando Norris, passant de la 2e à la 1re position, tandis que Lando Norris est passé de la 1re à la 3e position.

Note (1 à 5) :

---

## 19/30 · `strategy-2024-r13-VER-HAM`

**Question :** Pourquoi Lewis Hamilton a-t-il perdu sa place face à Max Verstappen lors de leurs premiers arrêts aux stands du Grand Prix de Hongrie 2024 ?

### Référence

- **Prémisse fausse :** Lewis Hamilton n'a pas perdu sa place face à Max Verstappen, c'est l'inverse : Lewis Hamilton a pris celle de Max Verstappen.
- **Cause principale :** l'undercut : Lewis Hamilton s'est arrêté le premier, au tour 16, 5 tours avant Max Verstappen, et a gagné 7.9 s sur le cycle d'arrêts
  - sur ses pneus durs neufs, il a tourné 1.28 s plus vite par tour que Max Verstappen, resté en piste sur des mediums de 21 tours, sur 3 tours comparables
  - son arrêt lui a aussi coûté 1.8 s de moins (19.7 s contre 21.5 s).
- **Écarts :** Max Verstappen avait 1.2 s d'avance à la fin du tour 15 ; à la fin du tour 22, Lewis Hamilton était devant de 6.8 s, et l'est resté au moins 3 tours.
- **Max Verstappen :**
  - arrêt au tour 21
  - mediums de 21 tours remplacés par des durs neufs
  - 21.5 s perdues au total sur les tours d'entrée et de sortie
- **Lewis Hamilton :**
  - arrêt au tour 16
  - mediums de 16 tours remplacés par des durs neufs
  - 19.7 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 20/30 · `strategy-2026-r09-LIN-BOR-held`

**Question :** Pourquoi Arvid Lindblad a-t-il perdu sa place face à Gabriel Bortoleto lors de leurs premiers arrêts aux stands du Grand Prix de Grande-Bretagne 2026 ?

### Référence

- **Prémisse fausse :**
  - Arvid Lindblad n'a pas perdu sa place face à Gabriel Bortoleto : il était devant avant leurs arrêts et l'est resté après. Gabriel Bortoleto a tenté l'undercut en s'arrêtant au tour 26
  - 1 tour avant Arvid Lindblad
  - mais n'a repris que 1.6 s sur le cycle
- **Écarts :** Arvid Lindblad avait 2.5 s d'avance à la fin du tour 25 ; à la fin du tour 28, Arvid Lindblad était devant de 1.0 s.
- **Arvid Lindblad :**
  - arrêt au tour 27
  - mediums de 27 tours remplacés par des durs neufs
  - 22.0 s perdues au total sur les tours d'entrée et de sortie
- **Gabriel Bortoleto :**
  - arrêt au tour 26
  - mediums de 26 tours remplacés par des durs neufs
  - 21.2 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Arvid Lindblad a perdu sa place face à Gabriel Bortoleto lors de leurs premiers arrêts aux stands du Grand Prix de Grande-Bretagne 2026 en raison d'un écart de temps qui s'est réduit, mais pas suffisamment pour dépasser son rival. Avant l'arrêt, l'écart était de -2.544 secondes, et après l'arrêt, il était de -0.978 secondes. Bien que l'écart se soit réduit de 1.566 secondes, cela n'a pas été suffisant pour que Lindblad dépasse Bortoleto.

Note (1 à 5) :

---

## 21/30 · `strategy-2025-r21-PIA-RUS`

**Question :** Pourquoi George Russell a-t-il perdu sa place face à Oscar Piastri lors de leurs premiers arrêts aux stands du Grand Prix de São Paulo 2025 ?

### Référence

- **Prémisse fausse :** George Russell n'a pas perdu sa place face à Oscar Piastri, c'est l'inverse : George Russell a pris celle d'Oscar Piastri.
- **Cause principale :** l'undercut : George Russell s'est arrêté le premier, au tour 34, 4 tours avant Oscar Piastri, et a gagné 20.5 s sur le cycle d'arrêts
  - sur ses pneus tendres usagés, il a tourné 2.21 s plus vite par tour qu'Oscar Piastri, resté en piste sur des mediums de 38 tours, sur 2 tours comparables
  - son arrêt lui a aussi coûté 12.8 s de moins (21.7 s contre 34.5 s).
- **Écarts :** Oscar Piastri avait 8.9 s d'avance à la fin du tour 33 ; à la fin du tour 39, George Russell était devant de 11.6 s, et l'est resté au moins 3 tours.
- **Oscar Piastri :**
  - arrêt au tour 38
  - mediums de 38 tours remplacés par des tendres usagés
  - 3.5 s immobile hors pénalité
  - 34.5 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 10 s pour avoir provoqué une collision purgée à cet arrêt
- **George Russell :**
  - arrêt au tour 34
  - mediums de 38 tours remplacés par des tendres usagés
  - 2.4 s immobile
  - 21.7 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> George Russell a perdu sa place face à Oscar Piastri lors de leurs premiers arrêts aux stands du Grand Prix de São Paulo 2025 car Oscar Piastri a effectué son arrêt au stand au 38e tour, alors que George Russell l'a fait au 34e tour. Après leurs arrêts, George Russell a gagné 20.521 secondes sur Oscar Piastri, passant de la 2e à la 3e place, tandis qu'Oscar Piastri est passé de la 1re à la 7e place.

Note (1 à 5) :

---

## 22/30 · `strategy-2024-r14-NOR-VER`

**Question :** Pourquoi Max Verstappen a-t-il perdu sa place face à Lando Norris lors de leurs premiers arrêts aux stands du Grand Prix de Belgique 2024 ?

### Référence

- **Prémisse fausse :** Max Verstappen n'a pas perdu sa place face à Lando Norris, c'est l'inverse : Max Verstappen a pris celle de Lando Norris.
- **Cause principale :** l'undercut : Max Verstappen s'est arrêté le premier, au tour 10, 5 tours avant Lando Norris, et a gagné 6.1 s sur le cycle d'arrêts
  - sur ses pneus durs neufs, il a tourné 1.42 s plus vite par tour que Lando Norris, resté en piste sur des mediums de 15 tours, sur 3 tours comparables
  - son arrêt lui a aussi coûté 0.6 s de moins (17.3 s contre 17.9 s).
- **Écarts :** Lando Norris avait 0.9 s d'avance à la fin du tour 9 ; à la fin du tour 16, Max Verstappen était devant de 5.2 s, et l'est resté au moins 3 tours.
- **Lando Norris :**
  - arrêt au tour 15
  - mediums de 15 tours remplacés par des durs neufs
  - 17.9 s perdues au total sur les tours d'entrée et de sortie
- **Max Verstappen :**
  - arrêt au tour 10
  - mediums de 10 tours remplacés par des durs neufs
  - 17.3 s perdues au total sur les tours d'entrée et de sortie
- Drapeau jaune au tour 15.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 23/30 · `strategy-2025-r05-VER-PIA`

**Question :** Au Grand Prix d'Arabie saoudite 2025, qui de Max Verstappen ou d'Oscar Piastri est sorti devant après leurs premiers arrêts aux stands, et pourquoi ?

### Référence

- Oscar Piastri est sorti devant Max Verstappen.
- **Cause principale :** la pénalité de Max Verstappen : une pénalité de 5 s pour avoir gagné un avantage en sortant de la piste, purgée à son arrêt du tour 21, où ses mécaniciens ont dû attendre 5 s avant de toucher la voiture
  - Oscar Piastri est ressorti devant avec 2.6 s d'avance seulement, moins que la pénalité.
- **Écarts :** Max Verstappen avait 2.8 s d'avance à la fin du tour 18 ; à la fin du tour 22, Oscar Piastri était devant de 2.6 s, et l'est resté au moins 3 tours.
- **Max Verstappen :**
  - arrêt au tour 21
  - mediums de 21 tours remplacés par des durs neufs
  - 3.3 s immobile hors pénalité
  - 24.8 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 5 s pour avoir gagné un avantage en sortant de la piste purgée à cet arrêt
- **Oscar Piastri :**
  - arrêt au tour 19
  - mediums de 19 tours remplacés par des durs neufs
  - 3.4 s immobile
  - 19.0 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Après leurs premiers arrêts aux stands, Oscar Piastri est sorti devant Max Verstappen. Max Verstappen a perdu du temps à cause d'une pénalité de 5 secondes pour avoir quitté la piste et gagné un avantage durable, ce qui a permis à Oscar Piastri de le dépasser en piste.

Note (1 à 5) :

---

## 24/30 · `strategy-2024-r16-LEC-NOR`

**Question :** Au Grand Prix d'Italie 2024, qui de Charles Leclerc ou de Lando Norris est sorti devant après leurs premiers arrêts aux stands, et pourquoi ?

### Référence

- Lando Norris est sorti devant Charles Leclerc.
- **Cause principale :** l'undercut : Lando Norris s'est arrêté le premier, au tour 14, 1 tour avant Charles Leclerc, et a gagné 3.3 s sur le cycle d'arrêts
  - ses pneus durs neufs lui ont donné l'avantage dès son tour de sortie, face à Charles Leclerc, encore sur des mediums de 15 tours
  - son arrêt lui a aussi coûté 2.0 s de moins (24.4 s contre 26.4 s).
- **Écarts :** Charles Leclerc avait 1.0 s d'avance à la fin du tour 13 ; à la fin du tour 16, Lando Norris était devant de 2.3 s, et l'est resté au moins 3 tours.
- **Charles Leclerc :**
  - arrêt au tour 15
  - mediums de 15 tours remplacés par des durs neufs
  - 26.4 s perdues au total sur les tours d'entrée et de sortie
- **Lando Norris :**
  - arrêt au tour 14
  - mediums de 14 tours remplacés par des durs neufs
  - 24.4 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Après leurs premiers arrêts aux stands, Lando Norris est sorti devant Charles Leclerc. Charles Leclerc a effectué son premier arrêt au stand au 15e tour, tandis que Lando Norris l'a fait au 14e tour. Avant leurs arrêts, Charles Leclerc était en deuxième position et Lando Norris en troisième position. Après leurs arrêts, Charles Leclerc est passé en septième position et Lando Norris en sixième position, ce qui signifie que Lando Norris a gagné une position sur Charles Leclerc.

Note (1 à 5) :

---

## 25/30 · `strategy-2024-r12-NOR-HAM-s2`

**Question :** Au Grand Prix de Grande-Bretagne 2024, qui de Lewis Hamilton ou de Lando Norris est sorti devant après leurs 2es arrêts aux stands, et pourquoi ?

### Référence

- Lewis Hamilton est sorti devant Lando Norris.
- **Cause principale :** le bon moment pour changer de pneus sur une piste qui évoluait : Lewis Hamilton est passé aux pneus tendres dès le tour 38, Lando Norris seulement au tour 39.
- **Écarts :** Lando Norris avait 1.9 s d'avance à la fin du tour 37 ; à la fin du tour 40, Lewis Hamilton était devant de 2.7 s, et l'est resté au moins 3 tours.
- **Lando Norris :**
  - arrêt au tour 39
  - intermédiaires de 12 tours remplacés par des tendres usagés
  - 23.6 s perdues au total sur les tours d'entrée et de sortie
- **Lewis Hamilton :**
  - arrêt au tour 38
  - intermédiaires de 11 tours remplacés par des tendres usagés
  - 24.6 s perdues au total sur les tours d'entrée et de sortie
- Pluie aux tours 38 et 39.

### Réponse du système

> Au Grand Prix de Grande-Bretagne 2024, Lewis Hamilton (HAM) est sorti devant Lando Norris (NOR) après leurs 2es arrêts aux stands. Hamilton a effectué son arrêt au stand au 38e tour, tandis que Norris a effectué le sien au 39e tour. Avant leurs arrêts, l'écart entre Hamilton et Norris était de 1,935 seconde en faveur de Norris. Après leurs arrêts, Hamilton a gagné 4,658 secondes sur Norris, ce qui lui a permis de passer devant et de prendre la première position, tandis que Norris est passé à la deuxième position.

Note (1 à 5) :

---

## 26/30 · `strategy-2025-r10-RUS-VER-held`

**Question :** Pourquoi George Russell a-t-il perdu sa place face à Max Verstappen lors de leurs premiers arrêts aux stands du Grand Prix du Canada 2025 ?

### Référence

- **Prémisse fausse :**
  - George Russell n'a pas perdu sa place face à Max Verstappen : il était devant avant leurs arrêts et l'est resté après. Max Verstappen a tenté l'undercut en s'arrêtant au tour 12
  - 1 tour avant George Russell
  - mais n'a rien repris
  - il a même perdu 0.3 s sur le cycle
- **Écarts :** George Russell avait 2.3 s d'avance à la fin du tour 11 ; à la fin du tour 14, George Russell était devant de 2.5 s.
- **George Russell :**
  - arrêt au tour 13
  - mediums de 16 tours remplacés par des durs usagés
  - 2.5 s immobile
  - 18.2 s perdues au total sur les tours d'entrée et de sortie
- **Max Verstappen :**
  - arrêt au tour 12
  - mediums de 15 tours remplacés par des durs neufs
  - 2.6 s immobile
  - 19.2 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> George Russell a perdu sa place face à Max Verstappen lors de leurs premiers arrêts aux stands du Grand Prix du Canada 2025 en raison d'un écart de temps qui s'est agrandi après leurs arrêts. Avant les arrêts, Russell avait un avantage de 2.27 secondes sur Verstappen. Après les arrêts, cet écart s'est transformé en un désavantage de 2.549 secondes, ce qui a entraîné une perte de positions pour Russell, passant de la 1ère à la 6ème place, tandis que Verstappen est passé de la 2ème à la 8ème place. Cependant, aucun des deux pilotes n'a dépassé l'autre lors de ces arrêts.

Note (1 à 5) :

---

## 27/30 · `strategy-2025-r22-SAI-LEC`

**Question :** Pourquoi Carlos Sainz a-t-il perdu sa place face à Charles Leclerc lors de leurs premiers arrêts aux stands du Grand Prix de Las Vegas 2025 ?

### Référence

- **Cause principale :** l'overcut : Charles Leclerc est resté en piste 2 tours de plus que Carlos Sainz (arrêts aux tours 22 et 24), et a gagné 1.4 s sur le cycle d'arrêts
  - son arrêt lui a aussi coûté 2.0 s de moins (20.6 s contre 22.5 s).
- **Écarts :** Carlos Sainz avait 0.6 s d'avance à la fin du tour 21 ; à la fin du tour 25, Charles Leclerc était devant de 0.8 s, et l'est resté au moins 3 tours.
- **Carlos Sainz :**
  - arrêt au tour 22
  - mediums de 22 tours remplacés par des durs neufs
  - 2.6 s immobile
  - 22.5 s perdues au total sur les tours d'entrée et de sortie
- **Charles Leclerc :**
  - arrêt au tour 24
  - mediums de 24 tours remplacés par des durs neufs
  - 2.7 s immobile
  - 20.6 s perdues au total sur les tours d'entrée et de sortie
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> Carlos Sainz a perdu sa place face à Charles Leclerc lors de leurs premiers arrêts aux stands du Grand Prix de Las Vegas 2025 en raison d'un undercut. Charles Leclerc a effectué son arrêt un tour plus tard, ce qui a permis de réduire l'écart de temps entre les deux pilotes. Avant les arrêts, Sainz avait un avantage de 0.563 secondes, mais après les arrêts, Leclerc a pris un avantage de 0.812 secondes, ce qui a entraîné une perte nette de 1.375 secondes pour Sainz. En conséquence, Leclerc a gagné une position, passant de la 4ème à la 9ème place, tandis que Sainz est passé de la 3ème à la 10ème place.

Note (1 à 5) :

---

## 28/30 · `strategy-2025-r23-ANT-SAI`

**Question :** Pourquoi Kimi Antonelli a-t-il perdu sa place face à Carlos Sainz lors de leurs premiers arrêts aux stands du Grand Prix du Qatar 2025 ?

### Référence

- **Cause principale :** un arrêt lent de Kimi Antonelli au tour 7 : 6.3 s immobile, contre 2.9 s pour Carlos Sainz, soit 3.4 s de plus, davantage que les 0.4 s qui les séparaient ensuite.
- **Écarts :** Kimi Antonelli avait 1.7 s d'avance à la fin du tour 6 ; à la fin du tour 8, Carlos Sainz était devant de 0.4 s, et l'est resté au moins 3 tours.
- **Kimi Antonelli :**
  - arrêt au tour 7
  - mediums de 7 tours remplacés par des mediums neufs
  - 6.3 s immobile
  - sous voiture de sécurité
- **Carlos Sainz :**
  - arrêt au tour 7
  - mediums de 7 tours remplacés par des mediums neufs
  - 2.9 s immobile
  - sous voiture de sécurité
- Drapeau jaune au tour 7.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 29/30 · `strategy-2026-r05-LEC-HAD`

**Question :** Pourquoi Charles Leclerc a-t-il perdu sa place face à Isack Hadjar lors de leurs premiers arrêts aux stands du Grand Prix du Canada 2026 ?

### Référence

- **Cause principale :** le double arrêt de l'écurie de Charles Leclerc : son coéquipier Lewis Hamilton est passé au stand juste avant lui au tour 31, et Charles Leclerc a dû attendre son tour : 4.8 s de plus que la médiane de la course dans la voie des stands.
- **Écarts :** Charles Leclerc avait 5.2 s d'avance à la fin du tour 30 ; à la fin du tour 32, Isack Hadjar était devant de 1.9 s, et l'est resté au moins 3 tours.
- **Charles Leclerc :**
  - arrêt au tour 31
  - tendres de 35 tours remplacés par des mediums neufs
  - sous voiture de sécurité virtuelle (VSC)
  - double arrêt de l'écurie
  - derrière son coéquipier Lewis Hamilton
- **Isack Hadjar :**
  - arrêt au tour 31
  - tendres de 35 tours remplacés par des mediums neufs
  - sous voiture de sécurité virtuelle (VSC)
  - double arrêt de l'écurie
  - derrière son coéquipier Max Verstappen
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :

---

## 30/30 · `strategy-2024-r24-VER-HAM`

**Question :** Pourquoi Max Verstappen a-t-il perdu sa place face à Lewis Hamilton lors de leurs premiers arrêts aux stands du Grand Prix d'Abou Dabi 2024 ?

### Référence

- **Cause principale :** la pénalité de Max Verstappen : une pénalité de 10 s pour avoir provoqué une collision, purgée à son arrêt du tour 29, où ses mécaniciens ont dû attendre 10 s avant de toucher la voiture
  - Lewis Hamilton est ressorti devant avec 2.1 s d'avance seulement, moins que la pénalité.
- **Écarts :** Max Verstappen avait 2.8 s d'avance à la fin du tour 28 ; à la fin du tour 35, Lewis Hamilton était devant de 2.1 s, et l'est resté au moins 3 tours.
- **Max Verstappen :**
  - arrêt au tour 29
  - mediums de 29 tours remplacés par des durs neufs
  - 3.5 s immobile hors pénalité
  - 32.5 s perdues au total sur les tours d'entrée et de sortie
  - une pénalité de 10 s pour avoir provoqué une collision purgée à cet arrêt
- **Lewis Hamilton :**
  - arrêt au tour 34
  - durs de 34 tours remplacés par des mediums usagés
  - 2.5 s immobile
  - 24.4 s perdues au total sur les tours d'entrée et de sortie
- Drapeau jaune au tour 31.
- Piste sèche, sans pluie pendant le cycle.

### Réponse du système

> (pas de réponse)

Note (1 à 5) :
