# ThermalCurve 1.0.0

[English](README_EN.md)

Guide d'installation et d'utilisation
© 2026 Valentin Legrand
Contact : valentin.legrand@emse.fr

ThermalCurve analyse des données de thermogravimétrie (ATG, ou TG) et de
calorimétrie différentielle à balayage (DSC). Il permet de corriger un blanc,
normaliser les signaux, comparer des essais, quantifier des zones et exporter
des résultats avec leur provenance. Les traitements fonctionnent localement.
L'interface est disponible en français et en anglais.

## Sommaire

1. [Installation et lancement](#1-installation-et-lancement)
2. [Repères dans l'interface](#2-repères-dans-linterface)
3. [Premier traitement pas à pas](#3-premier-traitement-pas-à-pas)
4. [Fichiers et unités](#4-fichiers-et-unités)
5. [Blanc, normalisation et signaux](#5-blanc-normalisation-et-signaux)
6. [Comparer des expériences et des répétitions](#6-comparer-des-expériences-et-des-répétitions)
7. [Définir et quantifier des zones](#7-définir-et-quantifier-des-zones)
8. [Personnaliser et exporter les graphiques](#8-personnaliser-et-exporter-les-graphiques)
9. [Enregistrer, déplacer et rouvrir un projet](#9-enregistrer-déplacer-et-rouvrir-un-projet)
10. [Calculs stœchiométriques](#10-calculs-stœchiométriques)
11. [Tableau périodique](#11-tableau-périodique)
12. [Résoudre les difficultés courantes](#12-résoudre-les-difficultés-courantes)
13. [Licence et contact](#13-licence-et-contact)

## 1. Installation et lancement

### Dossier Windows avec exécutable

Utiliser l'archive Windows x64 correspondant à la version souhaitée. Extraire
tout son contenu dans un dossier où vous avez accès en écriture, puis ouvrir
ThermalCurve.exe. Ne pas lancer l'application directement depuis l'archive.
Conserver le dossier _internal et les autres fichiers livrés près de l'exécutable.
Pour déplacer l'application, copier le dossier complet.

Cette édition embarque Python et les bibliothèques nécessaires. Il n'est pas
nécessaire d'installer Python, de créer .venv ou de disposer des droits
administrateur pour lancer l'application dans votre dossier personnel.
La cible est Windows x64. Les autres systèmes ne sont pas couverts par ce binaire.
Le binaire a été vérifié localement sous Windows 11 Entreprise 64 bits.
Un exécutable non signé peut déclencher un avertissement Windows : vérifier sa
provenance et l'empreinte fournie avec l'archive avant de décider de l'exécuter.

### Depuis les sources Python

Prérequis : Python 3.14.6, 64 bits. La plage déclarée est >=3.14.6 et <3.15 ;
la version vérifiée est 3.14.6. Installer Python depuis python.org si nécessaire.
Extraire les sources dans un dossier personnel et ouvrir PowerShell dans ce
dossier (celui contenant run_qt.py et requirements.txt).

Pour une nouvelle installation sans environnement .venv existant :

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_qt.py
```

Les deux premières commandes ne sont nécessaires qu'à l'installation.
Pour les lancements suivants, utiliser la troisième. Une connexion est nécessaire
pour obtenir les bibliothèques à l'installation, pas pour les calculs ensuite.

Bibliothèques directes vérifiées :

```text
PySide6 6.11.1       interface graphique
Matplotlib 3.11.1   graphiques
NumPy 2.5.1         calcul numérique
pandas 3.0.3        tableaux de données
openpyxl 3.1.5      lecture XLSX
xlrd 2.0.2          lecture XLS
```

pip installe aussi leurs dépendances. requirements.txt fixe ces six versions.

.venv est recommandé pour isoler ces bibliothèques des autres applications.
Son activation PowerShell n'est pas nécessaire. Il reste facultatif : avec un
Python compatible disposant déjà des dépendances, "py -3.14 run_qt.py" suffit.
Ne pas copier .venv d'un ordinateur à l'autre ; recréer l'environnement à la
nouvelle destination. Le dossier avec ThermalCurve.exe évite cette préparation.

## 2. Repères dans l'interface

Le bandeau supérieur donne accès à Fichier, Comparaison des expériences,
Calculs stœchiométriques, Tableau périodique, Options et À propos.

Dans Options > Langue, choisir Français ou English. Fermer puis relancer
l'application pour appliquer la langue à toute l'interface.
Dans Options > Apparence, choisir le style Atelier ou Console et le thème Clair
ou Sombre. La disposition change, les calculs restent les mêmes. Les panneaux
peuvent défiler ou se replier selon le style ; déplacer leurs séparateurs pour
répartir l'espace. Les préférences sont conservées entre les lancements.

Le parcours ATG montre les signaux de masse. Le parcours ATG-DSC permet aussi
de travailler avec le flux de chaleur disponible. Le graphique principal montre
une expérience active ; la comparaison possède sa propre sélection de courbes.
Les panneaux Préparation, Zones et État et messages accompagnent le graphique.

## 3. Premier traitement pas à pas

1) Cliquer sur Ajouter des expériences et sélectionner un ou plusieurs fichiers.
   Ils s'ajoutent à la liste. Sélectionner l'expérience à afficher.
2) Vérifier son nom, les signaux reconnus et les messages de lecture. Commencer
   avec une copie représentative si le format instrumental est nouveau.
3) Dans Blanc associé, garder Aucun pour observer les données sans correction,
   ou choisir un blanc adapté. Choisir un fichier permet d'en charger un nouveau.
4) Choisir l'axe horizontal : temps en secondes/minutes, température du four ou
   de l'échantillon. Cocher TG, dTG et/ou Flux de chaleur selon les données.
5) Régler les représentations dans Préparation, puis utiliser Traiter et afficher.
   Lire les messages avant d'interpréter les courbes et vérifier leurs unités.
6) Enregistrer un projet par Fichier > Enregistrer sous. Choisir un nouveau nom
   en .atgproj. Exporter séparément les résultats pour les partager.

Exemple simple : observer une TG sans blanc, saisir m0 en mg si nécessaire,
choisir Masse résiduelle (%), traiter et examiner la courbe. Ajouter ensuite un
blanc uniquement si ses lignes et ses temps correspondent à ceux de l'expérience.

## 4. Fichiers et unités

Le sélecteur accepte XLS, XLSX, TXT, CSV et TSV. Le contenu compte aussi : un .xls
peut être un classeur binaire, un XLSX ou un export textuel. Une extension reconnue
ne garantit pas que les colonnes de n'importe quel fichier soient interprétables.
Le lecteur recherche les en-têtes instrumentaux et conserve les métadonnées.
Les formats texte pris en charge comprennent UTF-8, UTF-16 avec BOM et Windows-1252.

Un exemple de texte simple utilise une description, une ligne de colonnes, une
ligne d'unités et les données. Les espaces ci-dessous représentent des tabulations :

```text
Exemple synthétique
Temps    Température du four    TG    HeatFlow
min      °C                     mg    mW
0        25                     20    2
1        35                     19    3
2        45                     18    4
```

Garder les unités dans les fichiers. Une température absente interdit son usage
comme axe ; un flux de chaleur absent ne peut pas être inventé. Consulter les
avertissements pour une colonne ignorée ou une unité incompatible. Les originaux
ne sont pas réécrits pendant le traitement.

## 5. Blanc, normalisation et signaux

### Blanc

Chaque expérience peut avoir son propre blanc, ou aucun. Ctrl+B permet d'associer
un fichier à l'expérience active. Dans la comparaison, Associer un blanc permet
une affectation aux expériences sélectionnées.

La soustraction est positionnelle : signal corrigé[i] = expérience[i] - blanc[i].
Le moteur contrôle les longueurs et la compatibilité des temps. Il n'interpole
ni ne rééchantillonne le blanc. Changer l'axe d'affichage ne change pas ce calcul.
Un signal absent du blanc ou incompatible reste signalé comme non corrigé.
Sans blanc, un résultat traité ne doit pas être interprété comme corrigé du blanc.

### Masses et TG

m0 est la masse initiale de l'expérience, en mg. Vérifier la valeur détectée et
sa provenance ; utiliser Saisir m0 manuellement lorsque nécessaire.
m_ref est une masse de référence de normalisation, aussi en mg. Pour une référence
personnalisée, renseigner sa valeur et son nom. La reprise de m0 comme référence
doit être explicite ; les deux masses ont des rôles distincts.

Les représentations TG comprennent : signal original, variation Δm ramenée à zéro
au premier point valide, Δm/m0 (%), masse restante en mg, masse résiduelle (%),
et variation normalisée par m_ref en mg/mg ou en %. Choisir la représentation,
renseigner les masses requises et traiter. Une masse invalide bloque la conversion
qui en dépend ; elle n'est pas remplacée arbitrairement.

### dTG

Choisir la dTG originale, normalisée par masse ou relative (%), puis son unité
de temps Source, min^-1 ou s^-1. Calculer dTG si absente produit une dérivée
numérique de la TG disponible. Cette dérivée est une donnée calculée ; le bruit
de mesure peut y être accentué. Vérifier le signal, l'unité et les messages.

### Flux de chaleur

Choisir le signal original, une remise à zéro, W, mW/mg, W/g ou W/mg selon les
options proposées. La normalisation massique utilise la référence renseignée.
Pour le zéro, choisir Premier point valide ou Moyenne sur une plage. Dans le
second cas, choisir l'axe et les bornes de la plage dans les unités indiquées.
Une référence absente ou non exploitable ne produit pas une conversion valide.

Aligner les zéros aligne visuellement les axes verticaux, sans déplacer les données.
Les unités des axes et l'état original/corrigé/normalisé permettent de savoir ce
qui est affiché. Le signe du flux dépend du signal instrumental ; ne pas déduire
exo/endothermique sans connaître sa convention.

## 6. Comparer des expériences et des répétitions

Ouvrir Comparaison des expériences dans le bandeau. Ajouter les essais souhaités,
cocher leur visibilité et choisir leur état Original, Corrigé ou Normalisé.
Sélectionner une ligne pour adapter son style, sa couleur ou son décalage Y ;
modifier le nom de légende et utiliser les flèches pour changer l'ordre.
Les réglages de blanc et de normalisation sont propres à chaque expérience.

Choisir l'axe, les signaux et Union des domaines ou Recouvrement commun. Chaque
courbe individuelle conserve ses propres abscisses. Empiler ajoute des décalages
visuels ; Remettre à zéro efface ces décalages. Ils ne modifient pas la mesure.

Pour des répétitions :

1) Sélectionner les essais constituant un même groupe physique.
2) Dans le panneau statistique, créer un groupe nommé avec ces membres.
3) Activer le mode statistique ; choisir Moyenne seule, Moyenne avec bande
   ±1 écart-type, Moyenne avec courbes individuelles ou Courbes individuelles seules.
4) Garder le pas automatique ou fixer le nombre de points. Lire le résumé des
   courbes incluses/exclues et vérifier les unités avant de comparer des groupes.
5) Utiliser Exporter dans ce panneau pour obtenir les statistiques du groupe.

Le calcul statistique peut interpoler sur une grille commune selon les domaines
et réglages choisis. Cette étape est distincte du tracé individuel et de la
correction du blanc. L'effectif peut varier selon l'abscisse. L'écart-type est
celui d'un échantillon (ddof=1), indéfini avec moins de deux valeurs. Une bande
±1 écart-type n'est pas un intervalle de confiance.

## 7. Définir et quantifier des zones

Dans Zones, choisir d'abord l'axe d'affichage adapté, nommer la zone, saisir ses
bornes et cliquer sur Ajouter. Sélectionner sur le graphe permet aussi de définir
les bornes par un glissement sur le graphique ; désactiver le zoom/panoramique
si ces outils capturent le geste. Modifier actualise la zone sélectionnée et
Supprimer la retire. Une zone garde son axe de définition.

Choisir Aucune ou Constante pour la ligne de base du flux de chaleur. Avec
Constante, renseigner sa valeur dans l'unité du signal concerné. Lire le résumé
de la zone active ou ouvrir Afficher tous les résultats pour le rapport complet.

Le rapport distingue les variations de masse, les extrema et les informations
disponibles sur le flux. L'intégration du flux se fait sur le temps, même si
la sélection utilise une température. Les aires de part et d'autre de la ligne
de base restent distinctes. Les portions hors zone ne sont pas reliées.

Une zone thermique peut être traversée en chauffe puis en refroidissement :
tous les passages sont conservés. Pour isoler un événement, préférer une zone
temporelle. Ne pas interpréter une variation globale ambiguë comme un passage unique.

Dans la comparaison, les rapports suivent le mode individuel ou statistique
affiché et utilisent les valeurs sans décalage visuel. Pour une moyenne de groupe,
le rapport donne les bornes, la variation et les extrema du signal moyen. L'enveloppe
de variation issue de la bande ponctuelle n'est ni l'écart-type de la variation
ni un intervalle de confiance. Elle ne constitue pas une intégrale calorimétrique.

## 8. Personnaliser et exporter les graphiques

La barre sous le graphique permet de revenir à la vue initiale, parcourir les
vues, déplacer, zoomer et enregistrer une image. Paramètres du graphique donne
accès au titre, à la légende, aux polices, aux axes et graduations, aux courbes,
aux lignes de référence et aux annotations. Une échelle logarithmique exige
des valeurs compatibles. Appliquer valide les réglages ; annuler préserve la
présentation précédente. Un modèle .atgstyle.json permet de réutiliser un style.

Fichier > Exporter le résultat (Ctrl+E) exporte le résultat de l'expérience active.
Choisir CSV ou TSV, un dossier et un nom nouveaux. Le fichier JSON associé
conserve sources, unités, paramètres, avertissements et provenance.
CSV : séparateur point-virgule, virgule décimale, UTF-8 avec BOM.
TSV : tabulations, point décimal, UTF-8.

Dans la comparaison, Exporter les données exporte les séries du mode sélectionné.
Chaque bloc de colonnes garde ses abscisses et sa longueur ; des cellules vides
complètent les séries plus courtes. Exporter la figure propose PNG, SVG et PDF.
Conserver les JSON avec les tableaux pour permettre leur interprétation ultérieure.
Ne jamais choisir un fichier source ou le projet ouvert comme destination.

## 9. Enregistrer, déplacer et rouvrir un projet

Ctrl+S enregistre ; Ctrl+Maj+S choisit une nouvelle destination. Ctrl+O ouvre un
projet .atgproj ; Ctrl+N prépare un nouveau projet. L'astérisque dans le titre
signale des modifications non enregistrées.

Un projet conserve les références et empreintes des sources, les blancs,
réglages, zones, comparaisons et données des outils. Il ne contient pas les
tableaux expérimentaux complets. Pour archiver ou partager une session, conserver
le .atgproj ET tous ses fichiers sources et blancs, idéalement dans le même
dossier ou ses sous-dossiers. Un export CSV n'est pas une sauvegarde de session.

Si une source a été déplacée, utiliser la résolution proposée à l'ouverture.
Si son empreinte a changé, vérifier le fichier avant d'accepter cette source.
Enregistrer sous un nouveau nom pour garder une version précédente du projet.
Les fichiers expérimentaux sont protégés contre leur remplacement par la sauvegarde.

## 10. Calculs stœchiométriques

Ouvrir Calculs stœchiométriques dans le bandeau, puis :

1) Ajouter une équation et saisir, par exemple : CaCO3(s) -> CaO(s) + CO2(g).
2) Cliquer sur Vérifier. Contrôler les formules, les états et les masses molaires.
3) Si nécessaire, Équilibrer propose des coefficients ; Utiliser la proposition
   applique le résultat. Conserver les proportions saisies traite les contraintes
   de proportions lorsqu'une solution compatible existe.
4) Choisir Masses individuelles et saisir la masse de chaque réactif avec son
   unité, ou Masse totale pour un mélange condensé supposé stœchiométrique.
5) Cocher les équations à traiter et cliquer sur Calculer la sélection.
6) Lire les réactifs limitants, excès, produits et variation de masse condensée.
   Adapter l'unité et la notation décimale/scientifique, puis Copier le résultat.

Pour les gaz réactifs, choisir Masse finie, Pression partielle/volume/température,
ppm molaire ou ppmv, ou Gaz en excès. Vérifier les unités de chaque champ.
Les conversions PVT suivent les gaz idéaux. Déclarer un gaz en excès suppose
qu'il ne limite pas la réaction. Ne pas confondre ppmv et fraction massique.

Ces bilans sont théoriques. L'équilibrage atomique ne démontre pas qu'une réaction
est thermodynamiquement possible ou rapide dans vos conditions expérimentales.
Les espèces gazeuses et condensées doivent être correctement distinguées pour
interpréter une perte ou un gain de masse.

## 11. Tableau périodique

Ouvrir Tableau périodique dans le bandeau. Rechercher un nom, un symbole ou un
numéro atomique, puis sélectionner un élément pour consulter ses informations.
La fenêtre de détails et la copie d'informations permettent de réutiliser les
valeurs affichées. Le tableau contient les 118 éléments et fonctionne hors ligne.

Les masses du référentiel de calcul restent celles utilisées en stœchiométrie.
Les données Mendeleev embarquées enrichissent la consultation ; leurs masses ou
valeurs d'enrichissement ne remplacent pas silencieusement le référentiel de calcul.
Une propriété absente reste indisponible. La provenance et la licence MIT de
l'instantané Mendeleev v0.20.0 sont conservées dans les ressources livrées.

## 12. Résoudre les difficultés courantes

L'exécutable ne démarre pas : extraire à nouveau le dossier complet, vérifier
que _internal accompagne l'exécutable et utiliser un dossier personnel accessible.
Une copie de ThermalCurve.exe seule ne suffit pas.

Module Python introuvable : utiliser le même interpréteur pour pip et run_qt.py.
Reprendre la commande d'installation avec .venv\Scripts\python.exe.

Fichier non reconnu : vérifier le contenu, l'en-tête, l'encodage et les unités.
Renommer une extension ne corrige pas un contenu incompatible. Préparer une copie
de travail en conservant l'original instrumental intact.

Blanc refusé : vérifier les temps, le nombre de lignes et les unités. Un blanc
d'une autre acquisition ne devient pas compatible en changeant l'axe du graphique.

Courbe absente : vérifier l'expérience active, sa visibilité, les signaux cochés,
le parcours, les unités et les messages. Une moyenne sans bande peut manquer
de répétitions valides. Une normalisation exige des masses et références valides.

Projet incomplet après déplacement : retrouver aussi les sources et les blancs.
Langue inchangée : fermer et relancer après le choix dans Options > Langue.

Pour signaler un problème, indiquer la version visible dans À propos, les étapes,
le message exact et, si possible, un petit exemple anonymisé que vous êtes
autorisé à partager. Ne pas envoyer de données confidentielles par défaut.

## 13. Licence et contact

© 2026 Valentin Legrand. Code original sous PolyForm Noncommercial 1.0.0.
Le texte complet figure dans LICENSE.txt ; les conditions de ce texte s'appliquent.
Le code est disponible avec une restriction d'usage non commercial. Les
bibliothèques et données tierces conservent leurs propres licences, détaillées
dans THIRD_PARTY_NOTICES.txt et les notices livrées avec la distribution.

Questions, propositions et demandes relatives à la licence :
[valentin.legrand@emse.fr](mailto:valentin.legrand@emse.fr)

Références :
- <https://polyformproject.org/licenses/noncommercial/1.0.0>
- <https://docs.python.org/3/library/venv.html>
- <https://pyinstaller.org/en/stable/operating-mode.html>
