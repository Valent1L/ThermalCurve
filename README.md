# ThermalCurve 1.0.1

[English](README_EN.md)

Guide d'installation et d'utilisation
© 2026 Valentin Legrand
Contact : valentin.legrand@emse.fr

ThermalCurve analyse des données de thermogravimétrie (ATG, ou TG) et du couplage
ATG-DSC. La DSC seule n'est pas prise en charge dans cette version.

**Cette application est destinée exclusivement aux fichiers extraits des appareils
SETARAM. Les fichiers issus d'autres fabricants ne sont peut être pas pris en charge.**
L'acceptation d'une extension ne garantit pas la compatibilité de tous les exports
SETARAM : les colonnes, les unités et la structure doivent être reconnues.

L'application permet de corriger un blanc, normaliser les signaux, comparer des
essais, quantifier des zones et exporter des résultats avec leur provenance.
Les traitements fonctionnent localement. L'interface est disponible en français
et en anglais. Voir les changements dans [changelog.md](changelog.md).

## Sommaire

1. [Installation et lancement](#1-installation-et-lancement)
2. [Repères dans l'interface](#2-repères-dans-linterface)
3. [Premier traitement pas à pas](#3-premier-traitement-pas-à-pas)
4. [Fichiers et unités](#4-fichiers-et-unités)
5. [Blanc, normalisation et signaux](#5-blanc-normalisation-et-signaux)
6. [Comparer des expériences et des répétitions](#6-comparer-des-expériences-et-des-répétitions)
7. [Définir et quantifier des zones](#7-définir-et-quantifier-des-zones)
8. [Personnaliser et exporter les graphiques](#8-personnaliser-et-exporter-les-graphiques), [Programme thermique](#programme-thermique)
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
openpyxl 3.1.5      lecture XLSX et export de compatibilité
XlsxWriter 3.2.9    écriture XLSX rapide
xlrd 2.0.2          lecture XLS
```

pip installe aussi leurs dépendances. requirements.txt fixe ces sept versions.

.venv est recommandé pour isoler ces bibliothèques des autres applications.
Son activation PowerShell n'est pas nécessaire. Il reste facultatif : avec un
Python compatible disposant déjà des dépendances, "py -3.14 run_qt.py" suffit.
Ne pas copier .venv d'un ordinateur à l'autre ; recréer l'environnement à la
nouvelle destination. Le dossier avec ThermalCurve.exe évite cette préparation.

## 2. Repères dans l'interface

Le bandeau supérieur donne accès à Fichier, Programme thermique,
Calculs stœchiométriques, Tableau périodique, Options et À propos.

Dans Options > Langue, choisir Français ou English. Fermer puis relancer
l'application pour appliquer la langue à toute l'interface.
Les saisies et affichages numériques utilisent la virgule en français (`20,5`)
et le point en anglais (`20.5`), indépendamment de la langue de Windows, y compris
les masses et gaz du calculateur, les zones, le programme thermique et les axes.
Les valeurs restent numériques dans les exports Excel et gardent leur format
interne dans les projets ; les points des formules hydratées restent inchangés.
Dans le bandeau principal, les commandes Importer, Enregistrer, Exporter et
Exporter la figure sont à gauche ; le titre "Console d'analyse" est à droite.
L'interface Console (C) est la seule interface : sa disposition compacte est
conservée, avec des boutons et encadrés légèrement arrondis. Le style Atelier (A)
et son sélecteur ont été retirés ; une ancienne préférence Atelier ouvre Console.
Dans Options > Apparence > Thème, choisir Clair ou Sombre. Les panneaux peuvent
défiler ou se replier ; déplacer leurs séparateurs pour répartir l'espace.
Les séparateurs horizontaux et verticaux ont la même épaisseur. Lorsque les volets
se rétrécissent, les rangées de commandes passent à la ligne et les listes de choix
s'ajustent. Une largeur minimale protège les contrôles du rognage ; les noms de
fichiers longs n'élargissent plus les panneaux.
Le thème est conservé entre les lancements. Les calculs restent les mêmes.
En thème clair, le contour des cases à cocher est renforcé, y compris dans la
liste d'expériences, pour les distinguer des fonds blancs.

Le parcours ATG montre les signaux de masse. Le parcours ATG-DSC permet aussi
de travailler avec le flux de chaleur disponible. Le graphique principal superpose
les expériences cochées dans la liste. Sélectionner une ligne définit l’expérience
active pour ses réglages, sans changer les courbes cochées. Le volet Réglages
réunit Préparation, Statistiques et Courbes. Les zones ont leur propre volet. La comparaison ne nécessite
plus de fenêtre séparée.

## 3. Premier traitement pas à pas

L'arborescence de chaque expérience et le choix de courbe dans Courbes ne proposent
que ses signaux disponibles. Le flux de chaleur apparaît uniquement si sa colonne
est présente, quel que soit le format du fichier. Une dTG absente apparaît lorsque
son calcul est activé à partir de TG et du temps.

1) Cliquer sur Ajouter des expériences et sélectionner un ou plusieurs fichiers.
   Ils s'ajoutent à la liste et au graphique. Cocher ou décocher pour afficher
   ou masquer chaque expérience ; cliquer sur son nom pour régler cette expérience.
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

### Essayer les fichiers fournis

Le dossier `Exemple` est inclus intégralement dans les archives Windows et source,
avec les projets de démonstration `.atgproj` et leurs fichiers associés. Le dossier
`Exemple/ATG` propose une expérience CaCO3 et son blanc au format texte.

Le dossier `Exemple/ATG-DSC` contient `MgCl2.6H2O.xls` (expérience) et `Blanc.xls`
(blanc associé). Charger l'expérience, associer le blanc, puis traiter en mode
ATG-DSC. Pour obtenir la dérivée absente du fichier, cocher "Calculer dTG si absente".
Enregistrer vos essais et exports sous de nouveaux noms en conservant ces fichiers.

## 4. Fichiers et unités

Le sélecteur accepte XLS, XLSX, TXT, CSV et TSV. Le contenu compte aussi : un .xls
peut être un classeur binaire, un XLSX ou un export textuel. Une extension reconnue
ne garantit pas que les colonnes de n'importe quel fichier soient interprétables.
Le lecteur recherche les en-têtes instrumentaux et conserve les métadonnées.
Les formats texte pris en charge comprennent UTF-8, UTF-16 avec BOM et Windows-1252.
Les exports ATG classiques avec description, colonnes et ligne d'unités séparée
sont reconnus par leur contenu, même sous une extension `.XLS` ou sans extension.
Les unités `/°C`, `/s`, `/mg` et `/mg/min`, ainsi que les tabulations finales,
sont prises en charge. Pour un fichier sans extension, sélectionner
"Exports ATG texte avec ou sans extension" dans la boîte d'importation.

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
un fichier à l'expérience active. Dans la liste principale, la cellule Blanc
permet de choisir un fichier, de réutiliser un blanc déjà chargé ou de choisir
Aucun pour cette ligne, même lorsqu'une autre expérience est active.

**Le blanc doit impérativement être acquis avec le même programme thermique
expérimental que l'expérience** : mêmes températures de consigne, vitesses de
chauffe/refroidissement et durées des paliers. Il doit également avoir le même
pas de temps d'acquisition et le même nombre de points, avec des temps
correspondants point par point. Le même programme thermique ne suffit donc pas
si les paramètres d'acquisition diffèrent.

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
de temps Source, min^-1, s^-1 ou h^-1. Calculer dTG si absente produit une dérivée
numérique de la TG disponible. Cette dérivée est une donnée calculée ; le bruit
de mesure peut y être accentué. Vérifier le signal, l'unité et les messages.

Le champ "Lissage dTG calculée (points)" apparaît lorsque ce calcul est activé.
Par défaut, "Sans lissage" (1 point) conserve la dérivée actuelle. Une fenêtre
impaire de 3, 5, 7 points, etc. applique une moyenne glissante centrée à cette dTG,
avant la normalisation par masse. Aux extrémités, la moyenne utilise uniquement
les points disponibles. Une fenêtre dépassant la longueur de la courbe est refusée.
Le lissage peut atténuer ou élargir les pics ; il affecte les résultats dérivés et
les zones utilisant cette dTG. Il ne modifie ni la TG ni une dTG fournie par l'appareil.
Tous les points et leurs temps sont conservés. Le réglage est propre à l'expérience,
enregistré dans le projet et décrit dans les métadonnées d'export.

Le temps peut s'afficher en secondes, minutes ou heures sur le graphique, dans
les zones, les plages de référence, le programme thermique et les exports.
Les fichiers déclarant une unité horaire sont également lus. Les conversions
dTG sont numériques : 1 mg/min = 60 mg/h. La base interne reste Temps_s,
sans modifier les colonnes originales ni la correction du blanc.

### Flux de chaleur

Choisir le signal original, le flux relatif à la référence, W, mW/mg, W/g ou W/mg selon les
options proposées. La normalisation massique utilise la référence renseignée.
Pour le zéro, choisir Premier point valide ou Moyenne sur une plage. Dans le
second cas, choisir l'axe et les bornes de la plage dans les unités indiquées.
Le flux relatif vaut `HF - HF_référence` : par défaut, le premier point valide
vaut donc zéro. Cette option permet de comparer les variations des signaux avec
une même origine. Elle ne remplace pas la correction du blanc et ne corrige pas
une dérive de ligne de base. Une référence inexploitable bloque la conversion.

Aligner les zéros aligne visuellement les axes verticaux, sans déplacer les données.
Les unités des axes et l'état original/corrigé/normalisé permettent de savoir ce
qui est affiché. Le signe du flux dépend du signal instrumental ; ne pas déduire
exo/endothermique sans connaître sa convention.

## 6. Comparer des expériences et des répétitions

Dans la liste principale, ajouter les expériences et cocher celles à superposer.
Déplier une expérience avec sa flèche pour accéder à ses courbes TG, dTG et flux
de chaleur. Les lignes filles sont affichées en retrait, cases à cocher comprises. Un clic sur une case coche
ou décoche uniquement la courbe correspondante. Décocher une
expérience masque toutes ses courbes sans perdre leurs choix individuels.
Les cases TG, dTG et flux de chaleur au-dessus du graphique restent des filtres
généraux : une courbe apparaît si son expérience, sa propre case et son filtre
général sont cochés, et si les données correspondantes sont disponibles.

Choisir Original, Corrigé ou Normalisé pour chaque expérience. Sélectionner une
ligne pour modifier sa normalisation dans Préparation. Dans Réglages > Courbes,
choisir TG, dTG, Flux de chaleur ou Toutes les courbes pour régler la couleur,
l'épaisseur, le style, les marqueurs, leur espacement, la légende et le décalage Y.
Sélectionner directement une courbe fille sélectionne ses réglages dans ce même onglet.
Les modifications de Toutes les courbes s'appliquent à tous les signaux de cette
expérience. Ces réglages et les cases individuelles sont conservés dans le projet.
Les listes proposent 10 styles de ligne et 25 choix de marqueur, avec noms et
aperçus correspondant au tracé. En mode statistique affichant une moyenne, la
cible Moyenne des expériences cochées permet de modifier chaque signal moyen
indépendamment des expériences. La bande d'écart-type suit sa couleur et son
décalage. Les réglages des moyennes sont enregistrés dans le projet ; les calculs
et les données exportées restent indépendants des décalages visuels.

Retirer enlève l'expérience du projet sans effacer son fichier ; Monter et
Descendre changent l'ordre de la liste et du tracé. Chaque courbe conserve ses
propres abscisses, sans sélecteur de domaine. Dans Empilement, choisir l'axe puis
cliquer sur Empiler pour espacer les courbes individuelles cochées. L'écart peut
être automatique ou saisi dans l'unité de cet axe. Après application, le curseur
et le champ numérique ajustent directement l'écart, sans décaler les autres axes.
Remettre à zéro efface tous les décalages, y compris ceux des moyennes. L'empilement
est disponible lorsque les courbes individuelles sont affichées.

Pour des répétitions :

1) Cocher les expériences et les courbes à inclure dans les statistiques.
2) Dans Réglages > Statistiques, activer le mode statistique.
   Aucun groupe n'est à créer : pour chaque signal, le calcul suit automatiquement
   les cases cochées. La ligne active sert uniquement à choisir les réglages à éditer.
3) Choisir Moyenne seule, Moyenne avec bande ±1 écart-type, Moyenne avec courbes
   individuelles ou Courbes individuelles seules.
4) Garder le pas automatique ou fixer le nombre de points. Lire le résumé des
   courbes retenues et vérifier leurs unités.
5) Utiliser Exporter dans le bandeau supérieur pour enregistrer les données selon
   le mode affiché. Exporter la figure, à côté, enregistre le graphique.

Le calcul statistique peut interpoler sur une grille commune selon les domaines
et réglages choisis. Cette étape est distincte du tracé individuel et de la
correction du blanc. L'effectif peut varier selon l'abscisse. L'écart-type est
celui d'un échantillon (ddof=1), indéfini avec moins de deux valeurs. Une bande
±1 écart-type n'est pas un intervalle de confiance.

## 7. Définir et quantifier des zones

Le panneau Zones, sous le graphique, regroupe deux onglets : Définition et
Résultats. L'ancien onglet Zones des Réglages et les rapports textuels séparés
ont été retirés. Dans l'en-tête, le bouton + lance directement un glissement sur
le graphique ; Échap annule la sélection. Désactiver le zoom/panoramique si ces
outils capturent le geste. Le nom est proposé automatiquement.

Dans Définition, un double-clic permet de modifier le nom, une borne, la méthode
de ligne de base ou sa valeur ; Entrée valide. Le bouton Modifier ouvre l'édition
de la borne initiale de la zone sélectionnée, et Supprimer retire cette zone.
Une zone garde son axe de définition ; changer l'axe du graphique ne convertit
pas ses bornes. La roue crantée à gauche du nom règle sa couleur, l'épaisseur
des bornes, l'opacité du remplissage et la visibilité de sa ligne de base.
La couleur de la ligne de base est réglable séparément.
Deux boutons permettent aussi de choisir les couleurs de l'aire calculée,
au-dessus et au-dessous de la ligne de base, y compris pour la courbe moyenne.
Ces réglages visuels sont enregistrés dans le projet et ne changent pas les calculs.

Choisir Aucune ou Constante pour la ligne de base du flux de chaleur. Avec
Constante, renseigner sa valeur dans l'unité du signal concerné. Une constante
sans valeur explicite conserve le comportement existant : référence au premier
point de la zone. Les anciennes lignes de base linéaires restent prises en charge.

Résultats conserve une synthèse avec Zone en première colonne, puis les familles
TG, dTG et Flux de chaleur. Si plusieurs expériences sont affichées, leurs lignes
sont regroupées sous le nom de chaque expérience. Afficher tous les résultats,
dans l'en-tête du panneau, ouvre une fenêtre indépendante avec le tableau complet
et un défilement horizontal, sans recalcul ni remplacement de la synthèse.
L'affichage est limité à quatre chiffres significatifs, avec notation scientifique
si nécessaire ; les valeurs internes restent intactes. Les unités sont lisibles
en texte simple, sans LaTeX brut. Si elles diffèrent entre expériences, elles
figurent dans les cellules. Les avertissements restent accessibles en infobulle
et par le bouton Informations des zones. Cette fenêtre dédiée rassemble les
bornes, références, états et avertissements ; le groupe Contexte est retiré
du tableau des résultats. Les dimensions initiales s'adaptent au contenu ;
les séparations entre en-têtes permettent ensuite de redimensionner les colonnes.
Les séparateurs restent alignés entre l'en-tête et les lignes, y compris pendant
le défilement. Le contour du tableau reste neutre au focus ; les champs de saisie
et listes déroulantes sont contenus dans leur cellule.
Les en-têtes de famille (TG, dTG, Flux de chaleur) sont fusionnés
sur leurs colonnes et restent lisibles pendant le défilement horizontal. Des
séparateurs plus contrastés distinguent ces familles dans l'en-tête et les lignes. Le
dimensionnement utilise la police réellement affichée après ouverture ou changement
de thème ; les noms d'expériences fusionnés ne gonflent pas la colonne Zone.
Le bouton Copier le tableau copie toutes les lignes de la vue active, y compris
celles hors écran, avec leurs en-têtes et identifiants lisibles, pour Excel ou
un fichier texte. La copie utilise la précision disponible, sans l'arrondi d'affichage.
La fenêtre complète possède son propre bouton de copie.

Le tableau distingue les variations de masse, les extrema et les informations
disponibles sur le flux. L'intégration du flux se fait sur le temps, même si
la sélection utilise une température. Les aires de part et d'autre de la ligne
de base restent distinctes. Les portions hors zone ne sont pas reliées.

Δm/m₀ (%) utilise la masse initiale m₀ de chaque expérience, lue dans les métadonnées
ou saisie en mg dans Réglages > Préparation. Cette saisie fonctionne aussi quand TG
reste affichée en mg. Une masse absente est signalée dans les infobulles ; elle
n'est jamais déduite du premier point TG, qui peut représenter une variation nulle.
Pour une moyenne TG en mg, le rapport est `100 × ΔTG_moyenne / moyenne(m₀)` sur les
expériences réellement incluses. Toutes leurs masses doivent être connues.
Si la courbe moyenne est déjà exprimée en Δm/m₀ (%), sa différence entre les bornes
donne directement le résultat. Les décalages visuels n'interviennent pas.

Une zone thermique peut être traversée en chauffe puis en refroidissement :
tous les passages sont conservés. Pour isoler un événement, préférer une zone
temporelle. Ne pas interpréter une variation globale ambiguë comme un passage unique.

Les rapports du graphique principal suivent le mode individuel ou statistique
affiché et utilisent les valeurs sans décalage visuel. En mode statistique, la
même synthèse rassemble TG, dTG et Flux de chaleur sur une ligne par zone.
Le nom de la moyenne figure au-dessus du tableau, sous Afficher tous les résultats,
et reste inclus dans la copie. Les indicateurs sont calculés sur la courbe moyenne affichée,
et non en moyennant les indicateurs individuels. Le mode avec courbes individuelles
conserve également leurs résultats, regroupés par expérience.

Les pics de flux tiennent compte de la ligne de base. Les aires signée, positive
et négative utilisent les mêmes règles d'intégration que les expériences.
L'aire de la moyenne exige un axe temporel : aucune durée n'est inventée sur un
axe de température. Les bornes sont interpolées sans extrapolation ni franchissement
de lacunes. Les unités suivent celles du signal moyen, y compris pour la TG normalisée.
Les résultats nécessitant une référence de masse propre à la moyenne (pourcentages,
masse finale et résiduel) restent indisponibles lorsque cette référence n'est pas définie.

Le tableau complet ajoute les valeurs aux bornes et les extrema du signal moyen,
ainsi que les écarts-types aux bornes et l'enveloppe de variation en mode avec bande,
dans les familles correspondantes. Cette enveloppe n'est ni l'écart-type de la
variation ni un intervalle de confiance ; aucun écart-type des pics ou des aires
n'en est déduit.

## 8. Personnaliser et exporter les graphiques

La barre Matplotlib permet de revenir à la vue initiale, parcourir les vues,
déplacer, zoomer et enregistrer une image. Un clic sur le bouton Légende ouvre
directement "Modifier la légende", sans menu déroulant. La case "Afficher la légende"
dans cette fenêtre contrôle sa visibilité, sans modifier les courbes ; ce choix est
enregistré dans le projet. La fenêtre contient trois onglets :

- "Cadre" : aucun, rectangulaire ou arrondi ; remplissage facultatif, couleur et
  transparence du fond, couleur et épaisseur du contour, marges communes ou séparées
  (% de la hauteur de police), retour à la ligne avec largeur réglable en caractères.
- "Position" : coins, centres des côtés et centre du graphique ; positions extérieures
  droite, gauche, haute et basse calculées au-delà des axes, graduations et titres,
  y compris l'axe du programme thermique. La position personnalisée utilise des
  coordonnées en % du graphique ou de la figure, depuis le bas à gauche, une ancre
  et un ancrage sur le cadre ou son contenu. Le déplacement à la souris peut être
  bloqué horizontalement ou verticalement.
- "Texte" : libellé modifiable pour chaque entrée, police, taille, couleur, rotation,
  interligne, tabulations, alignement, nombre de colonnes et alignement des colonnes,
  gras, italique et souligné. Les boutons permettent
  d'insérer indices, exposants, lettres grecques, accents et symboles. "Texte littéral"
  désactive l'interprétation mathématique ; Les échantillons de courbe restent automatiques.

Les réglages de texte s'adaptent à la largeur de la fenêtre, avec défilement vertical si nécessaire.
Le style s'applique à la légende entière ; les libellés se modifient entrée par entrée,
sur le même fond que le cadre, sans rectangles blancs derrière le texte. La couleur
du texte, le fond et le contour choisis sont respectés à l'écran, en thème clair ou
sombre, et dans les exports. L'ancienne option de fond blanc séparé a été retirée.
Les libellés peuvent contenir des retours à la ligne.
"Rétablir le libellé automatique" rétablit
le nom produit par l'application. Appliquer valide les réglages ; Annuler abandonne
les modifications non appliquées. Les réglages et libellés sont conservés dans le
projet et les exports de figure, sans renommer les sources ni modifier les données.

Le bouton "Paramètres du graphique" regroupe les anciens accès Personnaliser et
Espacement dans une fenêtre entièrement traduite. "Général" contient le titre et
l'alignement. La légende garde son éditeur dédié ; l'onglet Courbes est retiré.

- "Grille" sépare les lignes majeures et mineures : visibilité, couleur, style et
  épaisseur. Les lignes mineures suivent les subdivisions définies pour les axes.
- "Axes et graduations" permet de choisir l'axe inférieur, supérieur, TG, dTG,
  flux de chaleur ou température programmée. Régler la visibilité des traits et
  des valeurs, la couleur et l'épaisseur du trait, son côté et ses flèches, puis
  la direction, la longueur, la couleur et l'épaisseur des graduations majeures
  et mineures. "Automatique" conserve le style par défaut et suit le thème.
  "Tous les axes" ou "Les deux axes X" copie l'apparence sans déplacer les axes.
  La seconde vue donne accès aux libellés, bornes, échelles et formats des valeurs
  de chaque grandeur mesurée. L'axe supérieur partage l'abscisse et la graduation
  de l'axe inférieur, avec une apparence indépendante ; il suit aussi le zoom.
  Avec un seul axe vertical, le bord opposé ferme le cadre : noir par défaut à
  l'export, il suit la couleur, l'épaisseur et la visibilité du trait de cet axe.
- "Espacement" regroupe les marges automatiques ou manuelles du graphique et
  l'espacement des axes, de leurs noms et de leurs graduations.
- Les lignes de référence, polices et annotations restent disponibles dans leurs
  onglets. La fenêtre et les pages défilantes s'adaptent aux petites dimensions.

Les réglages sont conservés dans le projet et les exports PNG, SVG et PDF, sans
modifier les données ni les calculs. Une échelle logarithmique exige des valeurs
compatibles. Appliquer valide les réglages ; Annuler abandonne les modifications
non appliquées. Réinitialiser conserve la légende et les styles de courbes.
Un modèle .atgstyle.json permet de réutiliser une présentation.

Les boutons de couleur sont entièrement remplis par la couleur choisie. Cliquer ouvre
le sélecteur ; le code hexadécimal reste disponible dans l'infobulle.
Le rendu réutilise le placement automatique de la légende à géométrie identique
pendant une même image. Son déplacement redessine uniquement la légende lorsque
le moteur graphique le permet. Aucun point ni précision des courbes n'est retiré.
L'icône ThermalCurve est fournie en plusieurs tailles et configurée pour la fenêtre
et l'exécutable Windows lors de sa construction.
Dans la liste des expériences, la colonne Blanc affiche un seul libellé par
cellule. Elle est redimensionnable et l'infobulle donne le chemin complet.

Fichier > Exporter le résultat (Ctrl+E) produit un classeur Excel `.xlsx` avec :

1. "Données corrigées" : abscisses et signaux traités, y compris les conversions
   calculées, sans la colonne interne `Dans_zone_commune`.
2. "Données initiales" : colonnes et valeurs initiales de l'expérience.
3. "Données du blanc" : colonnes et valeurs initiales du blanc, ou une feuille
   vide signalée si aucun blanc n'est associé.

Dans les deux dernières feuilles, le nom complet du fichier figure en première
ligne et son chemin en deuxième ligne. Les unités figurent entre parenthèses à côté des noms de colonnes. La provenance
reste consultable dans les commentaires des titres des blocs. Aucun JSON annexe n'est
créé. Les anciens exports CSV/TSV sont remplacés par ce classeur.

Le bouton Exporter du bandeau et Fichier > Exporter le résultat (Ctrl+E) suivent
le même mode d’affichage du graphique principal :

- sans statistiques : toutes les séries visibles et compatibles ;
- "Moyenne" ou "Moyenne avec bande écart-type" : moyennes, écarts-types et effectifs ;
- "Moyenne avec courbes individuelles" : ces statistiques et les séries individuelles retenues ;
- "Courbes individuelles" en mode statistique : uniquement les séries cochées et compatibles retenues par le calcul.

Tous les exports du graphique utilisent la même présentation : nom du
fichier au-dessus du bloc, en-têtes avec unités et données en dessous. Les largeurs
des colonnes et les hauteurs des lignes sont ajustées au contenu à chaque export,
y compris pour les noms longs et les cellules contenant plusieurs lignes. Le nom
de l'expérience n'est pas répété dans chaque en-tête de colonne.
L'export des grands tableaux est optimisé en calculant les dimensions pendant
l'écriture et en réutilisant la mise en forme des données, tout en conservant les
trois feuilles, les valeurs et la provenance.
XlsxWriter accélère l'écriture sans réduire le nombre de points ni retirer de
mise en forme. La distribution Windows embarque ce moteur et sa licence ; les
utilisateurs n'ont pas à l'installer séparément.
L'export reste disponible avec openpyxl si XlsxWriter est absent
ou si un commentaire de provenance dépasse la limite du moteur rapide.
La durée dépend du volume exporté et de l'ordinateur ; une seconde n'est pas garantie.

La première feuille conserve l'état affiché (original, corrigé ou normalisé),
sans appliquer les décalages Y purement visuels. Les expériences initiales restent
dans la deuxième feuille, les blancs dans la troisième. Chaque jeu de données
occupe un bloc de colonnes séparé du suivant par une colonne vide. Les séries
gardent leurs propres abscisses et longueurs. Un même blanc partagé n'apparaît
qu'une fois. Ainsi, quatre essais partageant un blanc donnent quatre blocs
initiaux et un seul bloc de blanc, même lorsque seule la moyenne est exportée.
Les paramètres et exclusions sont consultables dans le commentaire du premier titre.

Exporter utilise ce même classeur pour les statistiques des expériences cochées.
Exporter la figure, dans le bandeau supérieur, propose PNG, SVG et PDF.
Ne jamais choisir un fichier source ou le projet ouvert comme destination.

### Programme thermique

Ouvrir "Programme thermique" dans le bandeau supérieur de la fenêtre principale.
Le programme est propre à l'expérience active et enregistré dans le projet.
En superposition ou en mode statistique, sa consigne est tracée si cette expérience
est cochée ; sélectionner une autre ligne permet d'afficher son programme.
Ajouter autant de sections que nécessaire : palier, montée ou descente.

- `T_ini` reprend automatiquement `T_f` de la section précédente.
- Pour un palier, les températures sont identiques et la durée est saisie en `hh:mm:ss`.
- Pour les durées et `t₀`, les `:` s'insèrent après deux chiffres saisis dans les heures et les minutes : `006600` donne `00:66:00`. Les minutes et secondes peuvent dépasser 59 et sont converties à la validation (`00:66:00` = `01:06:00`, `00:00:90` = `00:01:30`). Le collage d'une durée complète reste possible, y compris avec plus de deux chiffres par champ.
- Pour une rampe, saisir `T_f` et une vitesse β strictement positive en °C/min ou K/min.
  La durée est calculée par `abs(T_f - T_ini) / β`. Une vitesse nulle est refusée.
- La température s'affiche en °C ou K. L'origine `t₀` vaut `00:00:00` par défaut et reste modifiable.
- La saisie `01:06:00` s'affiche comme `66` minutes, `3960` secondes ou `1,1` heure selon l'axe choisi.

Cocher l'affichage du programme et appliquer. La courbe utilise un axe de
température à droite sur les graphiques temporels (secondes, minutes ou heures).
Elle représente la consigne saisie ; elle ne remplace pas la température mesurée.
L'espacement des axes droits et l'échelle de dTG préservent la lisibilité.
L'alignement des zéros suit une modification des bornes encadrant zéro ; des
bornes imposant des positions de zéro incompatibles sont refusées.

## 9. Enregistrer, déplacer et rouvrir un projet

Ctrl+S enregistre ; Ctrl+Maj+S choisit une nouvelle destination. Ctrl+O ouvre un
projet .atgproj ; Ctrl+N prépare un nouveau projet. L'astérisque dans le titre
signale des modifications non enregistrées.

Un projet conserve les références et empreintes des sources, les blancs,
réglages, zones, comparaisons et données des outils. Il ne contient pas les
tableaux expérimentaux complets. Pour archiver ou partager une session, conserver
le .atgproj ET tous ses fichiers sources et blancs, idéalement dans le même
dossier ou ses sous-dossiers. Un export Excel n'est pas une sauvegarde de session.

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

Les hydrates et adduits acceptent le point `.` et le point médian `·` :
`MgCl2.6H2O = MgCl2.4H2O + 2H2O(g)`. Le nombre après le point multiplie
la formule qui le suit. Les états omis sont considérés solides ; préciser `(g)`
pour l'eau dégagée. Les coefficients décimaux restent interdits ; utiliser une fraction.

Pour les gaz réactifs, choisir Masse finie, Pression partielle/volume/température,
ppm molaire ou ppmv, Gaz en excès, ou Débit × durée et composition. Vérifier les unités de chaque champ.
Les conversions PVT suivent les gaz idéaux. Déclarer un gaz en excès suppose
qu'il ne limite pas la réaction. Ne pas confondre ppmv et fraction massique.

Pour un volume fermé, saisir la pression partielle du réactif (ou la pression
totale et sa teneur en ppm), le volume et la température. Sous débit, saisir le
débit volumique total du mélange, la durée d'exposition en s, min ou h, la teneur
du réactif en % molaire, ppm molaire ou ppmv, ainsi que les pression totale absolue
et température de référence du débit. Ces dernières sont celles du débitmètre,
et non nécessairement celles du four. Les conventions de référence varient :
consulter la documentation de l'appareil, par exemple les [conditions Bronkhorst](https://www.bronkhorst.com/service-support/faq/?question=1925).
Le calcul utilise `n_gaz = fraction × P_ref × Q × durée / (R × T_ref)`, avec
débit et composition constants, selon le [modèle du gaz parfait](https://goldbook.iupac.org/terms/view/I02935).
Il quantifie le gaz apporté, pas la quantité réellement réagie.

Ces bilans sont théoriques. L'équilibrage atomique ne démontre pas qu'une réaction
est thermodynamiquement possible ou rapide dans vos conditions expérimentales.
La cinétique, la diffusion, les transferts de matière et de chaleur et l'équilibre
chimique ne sont pas modélisés. Le gain calculé pour `4 Fe(s) + 3 O2(g) = 2 Fe2O3(s)`
est donc un maximum stœchiométrique théorique.
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
