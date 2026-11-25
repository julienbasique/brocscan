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

## v1.4 — 25 novembre 2026 (après-midi, encore)

La publication sur GitHub : le code est en ligne, public, gratuit, pour
toujours accessible à tous.

- Dépôt : https://github.com/julienbasique/brocscan
- Contenu : le code, la licence MIT, la notice d'installation, ce journal.
  Jamais : les photos, l'historique des scans, aucun mot de passe.
- L'installation chez quelqu'un d'autre devient :
  `git clone https://github.com/julienbasique/brocscan.git` + la notice.

## v1.5 — 25 novembre 2026 (fin de matinée)

L'identification améliorée, mesurée sur 8 vrais scans de Julien (A/B avant/après) :

- **Nouvelle consigne moteur** : lecture PHOTO PAR PHOTO puis fusion ;
  l'objet SUJET (net, centré) est désormais clairement séparé des objets
  d'arrière-plan du bureau. Résultat mesuré : 8/8 bien identifiés, noms
  plus précis (la Casio devient « F-91W », la base Freebox nommée comme
  telle), vitesses identiques ou meilleures (1,8-3,5 s).
- **Filet anti-vide** : une réponse vide du modèle (comme hier 17 h, les
  lunettes d'enfant) est redemandée automatiquement une fois au même moteur.
- **« Prix réels » croisés avec l'estimation** : le bloc prix affiche
  maintenant « → Prix conseillé : X € » = médiane des vraies annonces,
  avec la phrase qui dit si l'estimation IA est dans le marché, plus
  chère ou moins chère que le marché.
- **Cache 10 min** des recherches « prix réels » : re-cliquer = instantané,
  et moins de navigations Chrome depuis l'IP maison.
- **BUG corrigé** : depuis la v1.3, l'app privée appliquait par erreur les
  quotas publics — après 1 recherche « prix réels » par heure, Julien
  tombait sur un blocage. L'app privée n'a désormais AUCUNE limite
  (retesté 3 appels d'affilée); les quotas restent sur la démo publique
  (retestés : 1er appel 200, 2e 429).

## v1.6 — 25 novembre 2026 (midi passé)

Les descriptions d'annonce font professionnelles :

- La rédaction par le moteur est cadrée : 3-5 phrases courtes et sérieuses,
  état réel AVEC les défauts (honnêteté), l'inclus annoncé si visible,
  aucun emoji, aucune majuscule criarde, aucun prix dans le texte.
- Le packaging par site est refait : plus de « photo1: », les inscriptions
  deviennent une ligne propre (« Marquages lisibles : CASIO F-91W WR100M ») ;
  eBay ne colle plus une « valeur estimée » dans le texte (le prix se règle
  dans le champ du site — une fourchette en texte fait amateur) ;
  Leboncoin parle « prix négociable pour achat groupé ».
- Exemple réel (montre Casio, générée) : « Je revends ma montre Casio
  F-91W dans sa version classique noire. C'est un grand classique du
  digital, fiable et à étanchéité 100m. La montre est en bon état de
  fonctionnement, sans cassure visible sur les photos. Je la remets en
  main propre ou l'envoie soigneusement emballée. »

## v1.7 — 25 novembre 2026 (jeudi midi)

Deux règles de rédaction de Julien appliquées et testées :

- **Ne dire que ce qui est sûr** : un accessoire (boîte, câble, notice) n'est
  annoncé que s'il est visible sur les photos ou dit dans les précisions ;
  et si personne n'a dit qu'il manque un truc, l'annonce n'invente AUCUNE
  absence. (Test A sans précision : rien d'inventé.)
- **À la première personne, toujours** : c'est Julien le vendeur — l'annonce
  ne dit plus jamais « d'après le vendeur » ; les précisions s'infiltrent
  naturellement (« Je la vends avec sa boîte d'origine… »). (Test B : la
  boîte du contexte est bien intégrée, aucune mention de « vendeur ».)

## v1.8 — 25 novembre 2026 (jeudi midi)

Un compteur de visites pour la démo (demande : « on a eu combien de visites ? ») :

- Table `stats` dans la base : pages vues de la démo / scans publics /
  recherches prix — comptés SEULEMENT sur l'instance publique (les usages
  privés de Julien ne gonflent pas le compteur). Survit aux redémarrages.
- Visible dans l'interface, ligne discrète en pied de page (apparait dès
  la première visite) + route /api/stats.
- Reprise des chiffres depuis l'ouverture (via les journaux serveur) :
  au 25/11 midi, AUCUNE page chargée de l'extérieur — tout le trafic
  public d'avant = tests de qualification de l'agent ; côté privé :
  1 session de Julien le matin (3 scans). Le compteur part de zéro,
  honnêtement, à partir de cette version.

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
