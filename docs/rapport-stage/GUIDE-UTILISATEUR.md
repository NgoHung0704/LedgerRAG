# LedgerRAG — Guide d'utilisation

> LedgerRAG répond à vos questions à partir de vos propres documents. Sa
> particularité est de savoir lire les **tableaux** — grilles, barèmes, tableaux
> croisés — et de refuser de répondre plutôt que d'inventer un chiffre.

Tout se passe sur le réseau interne. Aucun document, aucune question ne sort du
CETIAT.

**Version du guide :** 24/08/2026 · **Interface :** français, anglais, vietnamien,
espagnol, allemand (sélecteur en bas du bandeau de gauche).

---

## Sommaire

1. [En 30 secondes](#1-en-30-secondes)
2. [Poser une question](#2-poser-une-question)
3. [Lire une réponse](#3-lire-une-réponse)
4. [Gérer une base de connaissances](#4-gérer-une-base-de-connaissances)
5. [Ce que fait LedgerRAG de vos documents](#5-ce-que-fait-ledgerrag-de-vos-documents)
6. [Vérifier et corriger](#6-vérifier-et-corriger)
7. [Les assistants](#7-les-assistants)
8. [Intégrer un assistant dans une autre application](#8-intégrer-un-assistant-dans-une-autre-application)
9. [Écrans d'administration](#9-écrans-dadministration)
10. [⚠️ Précautions importantes](#10--précautions-importantes)
11. [En cas de problème](#11-en-cas-de-problème)

---

## 1. En 30 secondes

| Terme | Ce que c'est |
|---|---|
| **Base de connaissances** | Un corpus isolé de documents. Ex. « Politiques RH », « Conventions collectives ». Les bases ne se mélangent jamais entre elles. |
| **Document** | Un fichier déposé dans une base : PDF, Word, PowerPoint ou Excel. |
| **Assistant** | Un chat configuré : un périmètre de bases, un ton, un message d'accueil, un contact en cas de doute. C'est ce qu'utilisent les collègues au quotidien. |
| **Source / citation** | Le passage exact d'où vient une phrase de la réponse. Cliquable. |
| **Révision** | La file des tableaux que l'analyseur n'a pas su lire avec certitude, et qu'un humain doit regarder. |

**Le principe à retenir :** le système préfère dire « je ne suis pas sûr, voici
le tableau original » plutôt que de donner un chiffre plausible mais faux.
Quand une réponse porte un avertissement, ce n'est pas un défaut — c'est le
produit qui fait son travail.

---

## 2. Poser une question

### 2.1 Interroger toutes les bases — écran **Demander**

C'est l'usage courant. Tapez la question, le système choisit lui-même les bases
pertinentes d'après leurs descriptions et affiche lesquelles il a retenues.

> Pour que ce choix automatique fonctionne, **chaque base doit avoir une
> description** qui dit ce qu'elle contient. Voir §4.2.

Si vous savez déjà où chercher, restreignez à un groupe précis avec le sélecteur
de portée.

### 2.2 Interroger une seule base

Ouvrez la base, onglet **Discussion**. La recherche est limitée à ce corpus.
Utile quand deux bases contiennent des documents qui se ressemblent.

### 2.3 Écrire une bonne question

- **Nommez ce que vous cherchez comme le document le nomme.** « Coefficient
  285 » marche mieux que « le salaire du niveau intermédiaire ».
- **Une question à la fois.** Deux questions dans une phrase donnent une réponse
  qui en traite bien une et survole l'autre.
- **Les questions de suite fonctionnent** : « et pour 2024 ? » après une première
  question est comprise dans le contexte de la conversation.

Raccourcis : `Entrée` envoie · `↑` rappelle la question précédente.

---

## 3. Lire une réponse

### 3.1 Les citations dans le texte

Les sources apparaissent **à l'intérieur des phrases**, à l'endroit exact où
l'information a été utilisée. Cliquer ouvre le document à la bonne page.

L'aspect visuel a un sens :

| Aspect | Signification |
|---|---|
| **En gras** | Source fortement liée à la question. |
| Normal | Source pertinente. |
| Atténué | Source faiblement liée — à regarder d'un œil critique. |

Quand toutes les sources se valent, elles s'affichent toutes de la même façon :
le système ne fabrique pas une hiérarchie qui n'existe pas.

En bas de la réponse, la **liste complète des sources** reste affichée, y compris
celles qui ne sont citées dans aucune phrase.

### 3.2 « Voir aussi »

Une figure ou un graphique proposé sous ce libellé n'a **pas** servi à
construire la réponse — ses chiffres sont dans le dessin, le modèle ne les a pas
lus. Il vous est proposé **à regarder** parce qu'il se trouve sur une page
utilisée. Le distinguer des sources est volontaire.

### 3.3 La vérification des chiffres

Quand elle est activée sur la base, chaque chiffre de la réponse est recherché
dans les sources citées :

- **« *n* chiffres vérifiés dans les sources »** → ces chiffres ont été retrouvés
  tels quels dans un document.
- **« *n* chiffres n'ont pas pu être rattachés à une source »** → **vérifiez-les
  vous-même** avant de vous en servir. Le chiffre n'est pas forcément faux (il
  peut résulter d'un calcul), mais rien ne le confirme.

### 3.4 Les avertissements

| Avertissement | Ce que ça veut dire |
|---|---|
| *S'appuie sur la lecture d'une image ou d'un graphique* | La valeur vient de l'interprétation d'un visuel, pas de texte imprimé. |
| *Une source a été analysée avec une confiance faible* | L'analyseur a hésité sur ce tableau. Ouvrez l'original. |
| *Une source est signalée comme à vérifier* | Ce tableau attend une relecture humaine (§6). |
| *Un chiffre n'a pas pu être retrouvé dans les sources* | Voir §3.3. |

Un avertissement est suivi soit du nom d'un service à contacter, soit d'une
invitation à demander à une personne compétente.

### 3.5 Les retours 👍 / 👎

Signalez les bonnes et les mauvaises réponses : c'est ce qui permet de repérer
les documents mal lus sans avoir à tout relire.

---

## 4. Gérer une base de connaissances

### 4.1 Créer une base

**Bases de connaissances** → *Nouvelle base de connaissances*. Une base = un
corpus cohérent. Mieux vaut plusieurs bases bien décrites qu'une seule
fourre-tout : le routage automatique s'appuie sur cette séparation.

### 4.2 La description — le champ le plus important

La description **n'est pas un commentaire** : c'est ce que lit le routeur pour
décider si une question concerne cette base.

- ❌ « Base RH » — ne dit rien de ce qu'on peut y trouver.
- ✅ « Conventions collectives et grilles salariales, à partir de 2019. »

Le bouton **Proposer** rédige un brouillon à partir des documents déjà présents.
Relisez-le, il est là pour vous faire gagner du temps, pas pour décider à votre
place.

### 4.3 Format numérique des documents

Déclarez comment les nombres sont écrits dans vos documents (`7 462 639,50` en
français, `7,462,639.50` en anglais). Le déclarer évite au système de deviner —
et deviner, sur un séparateur de milliers, produit des erreurs d'un facteur 1000.

### 4.4 Vérifier les chiffres des réponses

Interrupteur dans les paramètres de la base, **activé par défaut**. Laissez-le
activé sur toute base contenant des chiffres qui engagent.

### 4.5 Déposer des documents

Onglet **Documents** : glissez vos fichiers, ou cliquez pour parcourir. Formats
acceptés : PDF, Word, PowerPoint, Excel.

L'ingestion tourne en arrière-plan, le statut se met à jour en direct :

| Statut | Sens |
|---|---|
| En file / En analyse / Indexation | En cours — patientez, un document long prend plusieurs minutes. |
| Terminé | Interrogeable. |
| Échec | Le message d'erreur est affiché sur la ligne. Voir §11. |

---

## 5. Ce que fait LedgerRAG de vos documents

Comprendre cette section vous fera gagner du temps en §6 : quand une réponse est
fausse, elle vous dit *où* regarder.

### 5.1 Le parcours d'un fichier

1. **Le fichier d'origine est conservé**, toujours. Rien ne le remplace.
2. **Word, PowerPoint et Excel sont convertis en PDF** une seule fois — ainsi ils
   passent par la même analyse vérifiée que les PDF, et gardent une image de
   chaque page.
3. **Chaque page est découpée en régions** : tableaux, figures, texte.
4. **Les tableaux sont photographiés puis lus** par un modèle de vision.
5. **Les figures** (graphiques, schémas) sont décrites : couleurs mesurées, puis
   description par le modèle.
6. **Le texte est remis dans l'ordre de lecture** — utile pour les diaporamas
   convertis, où l'ordre interne du fichier n'a rien à voir avec ce qu'on lit.
   Les en-têtes et pieds de page répétés sont repérés et écartés de la
   recherche.
7. Le tout est indexé pour la recherche.

**Deux règles de sécurité valent d'être connues :**

- Un tableau **sans bordures** est quand même détecté : le système regarde où
  les mots se placent, pas seulement les traits.
- **Une région dont le bord couperait un nombre est refusée**, même si c'est un
  trait du document qui l'a dessinée. `1 234,56` coupé en deux donnerait
  `1` et `234,56` — un chiffre crédible et faux. Le système préfère ne rien
  produire.

### 5.2 Les trois formes d'un tableau

Chaque tableau est conservé sous trois formes, et cela explique le
comportement que vous observez :

| Forme | À quoi elle sert |
|---|---|
| **Enregistrements** | Répondre exactement : « ligne *classe 11*, colonne *SMH* » |
| **Tableau affiché** | Vous le montrer, et vous permettre de le relire |
| **Résumé** | Permettre au tableau d'**être trouvé** par une question |

Un tableau bien lu mais mal résumé sera correct… et introuvable. C'est pourquoi
l'éditeur permet de corriger le résumé aussi.

### 5.3 Quand le système doute

Trois contrôles automatiques à l'analyse : la forme du tableau est-elle
cohérente avec le nombre de lignes extraites, deux lectures successives
donnent-elles la même chose, et les totaux tombent-ils juste. En cas de doute,
le tableau part en **Révision** (§6.1).

Quand le système signale, il a presque toujours raison. L'inverse n'est pas
vrai : **un tableau mal lu avec assurance n'apparaît pas dans la file**. C'est
pour cela que les sources restent toujours consultables.

---

## 6. Vérifier et corriger

### 6.1 L'onglet **Révision**

Les tableaux dont l'analyse est douteuse arrivent ici, chacun avec son image
d'origine à côté de la lecture qui en a été faite. Trois issues :

- **Valider** — l'analyse est bonne. L'alerte disparaît, les réponses citent ce
  tableau normalement.
- **Corriger** — ouvre l'éditeur (§6.2).
- **Rejeter** — l'analyse est fausse et non récupérable. Les données extraites
  **sortent de la recherche** ; l'image d'origine reste consultable.

### 6.2 L'inspecteur de document

Depuis la liste des documents, bouton **Inspecter**. Page par page, vous voyez
ce que le système a réellement extrait — pas ce qu'il affiche, ce qu'il a
compris.

**L'image découpée est l'autorité.** C'est contre elle que vous jugez, jamais
contre le texte extrait.

Les outils, regroupés par intention :

**Le contenu est faux**

| Outil | Quand l'utiliser |
|---|---|
| **Modifier** | Une valeur, un mot, un en-tête de colonne est faux. La correction est indexée immédiatement : la question suivante en profite. |
| **Recalculer** | Après avoir corrigé le tableau affiché à la main — reconstruit les données et le résumé à partir de vos corrections. **Sans cela, corriger l'affichage ne change pas les réponses.** |
| **Annuler** | Revenir à l'état d'avant votre dernière modification. |
| **Supprimer** | Un en-tête courant, un numéro de page, un fragment qui ne fait que polluer la recherche. |

**Demander au modèle de recommencer**

| Outil | Quand l'utiliser |
|---|---|
| **Relire la page** | La page est en colonnes, un diaporama, un schéma — et le texte est dans le désordre. Le modèle relit la page entière. |
| **Réanalyser plus fort** | Un tableau mal lu : il est re-photographié en double résolution et relu. **C'est une proposition — rien n'est enregistré sans votre accord.** |
| **Assistant d'édition** | Décrire en français la transformation voulue sur ce que vous êtes en train d'éditer. |

**Le découpage est faux** — le système a mal vu où commence et finit un tableau

| Outil | Quand l'utiliser |
|---|---|
| **Séparer** | Deux tableaux ont été entourés comme un seul. Symptôme : des lignes sans rapport dans la même grille. |
| **Fusionner** | Un tableau a été coupé en deux — souvent entre deux pages. Symptôme : un tableau sans en-tête, ou qui s'arrête au milieu. |
| **Promouvoir en tableau** | Une grille a été lue comme du texte. |
| **Rétrograder en texte** | Du texte mis en page a été pris pour un tableau. |
| **Cellules fusionnées** | Choisir si une valeur répétée s'affiche une fois ou à chaque ligne. Affichage seulement, les données ne changent pas. |

> **Corriger le découpage est souvent plus efficace que corriger le contenu.**
> Si un tableau est coupé au mauvais endroit, chaque valeur sera à reprendre une
> par une ; recoller le tableau et relancer l'analyse règle tout d'un coup.


---

## 7. Les assistants

Un assistant est ce que vous donnez à vos collègues. Écran **Assistants** →
*Nouvel assistant*.

| Réglage | À quoi ça sert |
|---|---|
| **Nom / description** | Ce que voit l'utilisateur. |
| **Bases attachées** | Le périmètre documentaire. Une même base peut servir à plusieurs assistants. |
| **Consignes** | Ton, format, priorités. **S'ajoutent** aux règles de sécurité, ne les remplacent jamais. |
| **Message d'accueil** | Ce qui s'affiche dans une conversation vide. Utilisez-le pour dire ce que l'assistant sait et ne sait pas. |
| **Contact en cas de doute** | Le service vers lequel orienter quand la réponse n'est pas certaine — ex. « service RH ». Laissé vide, l'assistant invite à demander à une personne compétente. |
| **Vérification des chiffres** | Peut surcharger le réglage des bases. |

**Partager des documents entre assistants** ne demande aucune manipulation :
attachez la même base aux deux assistants.

---

## 8. Intégrer un assistant dans une autre application

Un assistant peut apparaître directement dans une autre application intranet.

**Côté LedgerRAG :** *Assistants → l'assistant → Paramètres → **Intégrer dans une
autre application** → **Créer une intégration***. Un code `<iframe>` s'affiche, à
copier dans la page hôte.

> L'assistant doit être **enregistré** avant de pouvoir créer une intégration.

**Côté serveur — obligatoire :** déclarer qui a le droit d'afficher la page.

```bash
# dans le fichier .env du serveur
EMBED_FRAME_ANCESTORS=https://mon-application.interne
```

puis redémarrer. **Tant que cette variable n'est pas renseignée, le cadre reste
blanc** : la page refuse d'être encadrée par défaut. Ce n'est pas une panne,
c'est le comportement voulu.

Plusieurs origines se séparent par une virgule. Le paramètre `?lang=fr` dans
l'URL de l'`<iframe>` fixe la langue de la fenêtre intégrée.

**Révoquer** ou **Régénérer** une intégration : les boutons du même panneau.
Dans les deux cas le lien précédent cesse immédiatement de fonctionner — pensez
à mettre à jour le code `<iframe>` de la page hôte après une régénération.

> **À savoir :** tant que l'authentification n'est pas activée sur le serveur, ce
> jeton n'est pas un secret — toute personne sur le réseau interne accède déjà à
> l'application. Il sert à pouvoir couper un accès et à préparer l'activation de
> l'authentification.

---

## 9. Écrans d'administration

### Fournisseurs de modèles

Quel modèle assure chaque rôle (analyse des tableaux, discussion, embedding,
reranking), et si ce rôle répond. Trois informations à lire attentivement :

- **la couche qui a décidé** — `database`, `environment` ou `default`. Une valeur
  enregistrée en base **prend le pas sur le fichier `.env`** : si une
  modification du `.env` semble sans effet, c'est ici qu'on le voit ;
- **ce que dit l'environnement**, même quand il est masqué ;
- **la dernière erreur réelle** du rôle — différente d'un test de disponibilité :
  un rôle peut répondre au test et échouer en usage.

### Diagnostics

État des services (base de données, index vectoriel, stockage, file de tâches) et
outils de vérification de la chaîne d'ingestion.

### Journal d'audit

Traçabilité RGPD : dépôts de documents, questions posées, changements de
configuration.

---

## 10. ⚠️ Précautions importantes

### 9.1 Ne pas utiliser « Retraiter » pour le moment

> **Le bouton *Retraiter* d'un document ne doit pas être utilisé, et aucun
> nouveau document ne devrait être déposé, tant que les deux défauts de détection
> ouverts ne sont pas corrigés.**

Deux formes de tableaux sont aujourd'hui mal détectées :

1. un tableau dont **la première colonne est courte** avec des écarts larges
   (forme `A | 1 | 21 700`, très courante dans les documents RH) peut être
   enregistré **sans sa colonne d'étiquettes** — donc des chiffres sans dire à
   quoi ils correspondent ;
2. un tableau contenant une cellule où deux colonnes ont fusionné (un filet non
   imprimé) peut être **entièrement perdu**.

**Ce qui est déjà en base n'est pas affecté** : les corrections concernent la
chaîne d'analyse, et les documents déjà traités conservent leur lecture actuelle.
Le risque n'apparaît qu'au moment d'un retraitement ou d'un nouveau dépôt.

*Retirer cet avertissement dès que les deux défauts sont corrigés.*

### 9.2 Retraiter efface le travail manuel

Indépendamment du point précédent : retraiter un document **remplace ses
éléments actuels**. Les corrections, découpages et validations faits à la main
sont perdus.

### 9.3 Supprimer est irréversible

Supprimer un document efface son texte analysé, ses tableaux, ses vecteurs **et
le fichier d'origine**. Supprimer une base efface tout ce qu'elle contient, y
compris les historiques de conversation.

### 9.4 Ne jamais modifier le prompt d'analyse sans mesure

Réservé aux personnes qui touchent au code : une modification de formulation du
prompt de l'analyseur fait basculer des tableaux **sans rapport** entre 0 % et
100 %. Toute modification exige un A/B isolé sur `make eval-tables`.

---

## 11. En cas de problème

| Symptôme | Piste |
|---|---|
| Un document reste en **Échec** | Le message d'erreur figure sur sa ligne. Fichier protégé par mot de passe, PDF corrompu, ou rôle d'analyse indisponible → **Fournisseurs de modèles**. |
| Les réponses sont **très lentes** | Vérifier dans **Diagnostics** que l'inférence tourne bien sur GPU. Une bascule silencieuse sur processeur après une mise à jour est un incident connu : le système fonctionne, mais des dizaines de fois plus lentement. |
| Une question **ne trouve pas** un document pourtant présent | Vérifier son statut (**Terminé** ?) puis, dans l'**inspecteur**, ce qui a réellement été extrait de la page concernée. Un tableau non détecté n'est pas interrogeable. |
| Le routeur envoie la question à la **mauvaise base** | Les descriptions sont trop proches ou trop vagues (§4.2). En attendant, restreindre la portée à la main. |
| Beaucoup d'avertissements *« chiffre non rattaché »* | Souvent le **format numérique** de la base qui ne correspond pas aux documents (§4.3). |
| L'`<iframe>` reste **blanc** | `EMBED_FRAME_ANCESTORS` n'est pas renseigné, ou ne correspond pas exactement à l'origine de l'application hôte (protocole et port compris). Voir §8. |
| Une modification du `.env` **reste sans effet** | Une valeur enregistrée en base prend le dessus. **Fournisseurs de modèles** indique quelle couche a décidé (§9). |
| L'interface revient à une **autre langue** | Le choix est conservé dans un cookie du navigateur. Un mode privé ou un nettoyage des cookies le remet à la valeur par défaut (anglais). |

---

## Annexe — Exploitation

Commandes utiles sur le serveur (`/home/cetiat/LedgerRAG`) :

```bash
# Mettre à jour et redémarrer
git pull && docker compose up -d --build api frontend

# Vérifier avant démarrage (débit GPU, services)
./scripts/preflight.sh

# Sauvegarde
./scripts/backup.sh

# Suite de tests
make test           # tests unitaires, sans dépendance externe
make eval-qa        # qualité des réponses (nécessite le serveur et ses modèles)
make eval-detection # détection des tableaux sur pages réelles
```

Le déploiement complet est décrit dans [`docs/DEPLOY.md`](../DEPLOY.md).
