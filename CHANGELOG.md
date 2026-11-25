# BrocScan — les versions

Chaque version est une copie complète de l'app qui fonctionnait.
Si un jour quelque chose casse : on remet une ancienne version et on repart de là.

Les copies sont rangées dans :

- `/home/julien/brocscan-versions/` → un dossier par version (à ouvrir directement)
- historique technique interne : dépôt git dans `/home/julien/brocscan`

## v1.0 — 25 novembre 2026 (le matin)

La première version archivée — tout ce qu'on a construit jusqu'ici, vérifié :

- Scan de 1 à 3 photos + champ « précisions » → identification, état, fourchette de prix
- Moteur nuage (`glm-5.3-flash:cloud`, 2-5 s) en premier, modèle local (gemma4:e2b, ~20-30 s) en secours automatique
- Annonces prêtes à coller : Leboncoin, Vinted, eBay (+ liens des formulaires et « ventes terminées » eBay)
- Bouton « Prix réels du marché » : de vraies annonces Vinted lues dans un vrai Chrome (min / médiane / max)
- Historique des scans + photos stockés sur le PC (SQLite dans data/)
- Marche sur le PC (`http://localhost:8000`) et sur la télé via Tailscale (`http://100.113.18.49:8000`)
- Icône de bureau : tout démarre en 1 clic, sans agent

Vérifié le 25/11 au matin : serveur en marche, 67 scans dans l'historique
(dont ton téléphone DECT, le boîtier Raspberry Pi et la manette DualSense
de ce matin), prix réels Vinted retestés — 98 annonces DualSense, médiane 79 €.

## v1.1 — 25 novembre 2026 (peu après)

Version « prête à publier » : le paquet est propre pour être partagé.

- Notice « installer sur un autre ordinateur » dans le README (5 min, gratuit)
- Licence MIT (ce qu'on a le droit de partager : tout, avec le nom de Julien)
- Liste des dépendances exacte (il manquait la photo et le pilote Chrome dans le fichier)
- Vérifié : aucun mot de passe ni info personnelle dans le code publié

Le dépôt en ligne n'existe pas encore — reste à créer le compte/connexion
GitHub avec Julien, puis pousser. Zéro euro jusqu'ici et après.

## v1.2 — 25 novembre 2026 (midi)

La démo sur INTERNET : BrocScan accessible à tout le monde, gratuitement.

- Nouvelle adresse publique : `https://brocscan.tail598dc7.ts.net/` —
  n'importe qui, n'importe quel appareil, n'importe quel réseau (4G inclus),
  aucun compte à créer. Porte internet gratuite (Tailscale Funnel, HTTPS
  automatique, aucun réglage de box).
- Les visiteurs font la même chose que toi : photos → estimation → annonces,
  bouton « prix réels ».
- Ils ne peuvent JAMAIS voir tes scans ni tes photos : instance séparée
  (port 8001), historique masqué, photos inaccessibles, suppression bloquée ;
  leurs propres scans sont éphémères (rien sur le disque, rien dans ta liste).
- Garde-fous anti-abus (ta quota reste pour TOI en priorité) :
  4 analyses/heure par visiteur et 100/jour au total ; « prix réels » :
  1/heure et 12/jour ; l'instance publique pilote Chrome sans fenêtre
  (rien ne s'ouvre à l'écran de la maison).
- Ton app privée reste exactement comme avant (port 8000).
- Vérifié en testant depuis internet : 4 scans passés (lire « montre Casio
  F-91W », fourchette 8-25 €), le 5e bloqué avec le message en français ;
  Vinted marche même sans fenêtre (96 annonces, médiane 20 €) ; rien
  stocké (71 photos avant = 71 après).
- Après un reboot du PC : l'icône de bureau relance tout, porte internet incluse.

## v1.3 — 25 novembre 2026 (après-midi)

Sécurité du compte et de la démo publique.

- Nouvelle option « **code d'accès** » : quand elle est activée (le
  propriétaire choisit le code), la démo demande le code à chaque
  nouveau visiteur (mémorisé une fois par navigateur). Un mauvais code
  → refus clair en français, et il ne consomme pas de quota.
  Testé de bout en bout : sans code → « Code d'accès requis » ; avec le
  bon code → scan + prix réels passent. OFF par défaut (démo ouverte),
  ON sur demande.
- Vérifié ce que la porte internet expose : **UNE SEULE route**
  (Funnel : l'adresse publique → l'instance publique 8001). Ni le compte
  Tailscale, ni l'app privée, ni aucun réglage : personne ne peut
  « se connecter » à un compte via cette adresse — il n'y a aucun
  identifier sur cette porte, elle ne parle qu'à l'app.
- Rappel de ce qui était déjà verrouillé depuis v1.2 : instance publique
  séparée (127.0.0.1:8001), historique et photos invisibles, suppression
  bloquée, scans éphémères, quotas 4/h + 100/j et 1/h + 12/j.
- Le seul endroit du code où un abus pourrait toucher le compte Ollama
  reste le quota nuage — borné par les garde-fous ; et si un jour tu veux
  la démo SANS nuage du tout (0 risque pour ton compte, scans 20-30 s) :
  une ligne à changer.

## Avant : les étapes du même jour (24 novembre)

Les versions n'existaient pas encore — ces étapes intermédiaires ne sont pas
archivées en tant que code, elles sont racontées pour mémoire :

- **Début d'avant-midi** : le noyau — photo → gemma4:e2b (100 % local) →
  catégorie, fourchette, annonces, historique. Application web (PWA) sur le PC.
- **Vers 15 h 44** : les photos iPhone (HEIC/WebP) acceptées ; le modèle
  transcrit ce qu'il lit au lieu d'inventer des marques ; le serveur ne gèle
  plus pendant un scan ; le modèle reste en mémoire (scans suivants rapides).
- **Fin d'après-midi** : moteur nuage glm en premier (2-5 s au lieu de 20-30 s),
  repli local automatique si nuage indisponible ; l'annonce rédigée par le
  nuage ; badge qui dit quel moteur a servi.
- **Fin de journée** : annonces packaging par site (market.py) puis vrais prix
  du marché via Vinted dans un Chrome réel (marche.py) avec son bouton.

## Et après ?

Même méthode après chaque amélioration vérifiée : une copie par numéro dans
`~/brocscan-versions/`, sa ligne ici, un marqueur dans l'historique technique.
Tu n'as rien à faire — tu demandes un truc, je le code, je le teste, je
fabrique la nouvelle version.
