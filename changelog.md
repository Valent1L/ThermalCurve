# Changelog

## 1.0.1 - 2026-09-10

### Français

- Sécurité des imports : blocage des références réseau, lecteurs réseau et liens suivis automatiquement depuis un projet ; limites de taille, de décompression et de dimensions des tableaux, sans troncature. Protection XML par defusedxml 0.7.1, incluse dans les dépendances et la distribution avec sa licence. Sources locales, précision et calculs conservés.
- Documentation : explication de l'avertissement Windows SmartScreen pour l'exécutable non signé, vérification de provenance et d'empreinte, étapes de lancement et recours au service informatique sur les postes gérés, dans les guides français et anglais.
- Graphique avec un seul axe vertical : rétablissement du bord droit du cadre, noir par défaut à l'export et cohérent avec le style de l'axe. Correction commune aux expériences individuelles, superpositions et moyennes, sans ajout de graduations ni modification des données.
- Distribution 1.0.1 : inclusion des projets de démonstration `.atgproj` du dossier `Exemple` dans les archives, sans inclure les projets personnels situés hors de ce dossier.
- Éditeur de légende : réglages du texte disposés sur des lignes adaptables pour éviter le débordement horizontal avec la police de démarrage.
- Lecture des exports ATG classiques sous extension `.XLS` ou sans extension avec conservation de leur ligne d'unités. Filtre d'importation explicite pour les fichiers sans extension. Résultats Δm/m₀ individuels indépendants des erreurs de référence du flux ; prise en charge de Δm/m₀ et du résiduel pour les moyennes avec masses connues. La modification de m₀ seule marque le projet comme modifié. Boutons entièrement colorés. Icône vectorielle ThermalCurve et ICO multi-tailles configurés pour Qt et PyInstaller. Renommage du guide français en README.md et adaptation de la distribution. Placement de légende réutilisé uniquement à géométrie identique au sein d'un rendu et déplacement par rafraîchissement local, sans suppression de points.
- Renommage de Réglages > Affichage en Courbes. Édition indépendante des moyennes TG, dTG et flux de chaleur en mode statistique, avec bande d'écart-type assortie. Dix styles de ligne et 25 choix de marqueur nommés avec aperçus. Empilement par axe avec écart automatique, curseur et saisie numérique dans l'unité de l'axe. Styles des moyennes, décalages et écart enregistrés dans les projets, sans modifier les calculs ni les données exportées.
- Regroupement de Personnaliser et Espacement dans Paramètres du graphique, avec libellés français/anglais. Retrait des réglages de légende et de l'onglet Courbes. Onglet Grille séparant les styles majeurs/mineurs ; axes réglables individuellement, y compris en haut et pour la consigne thermique, avec copie de l'apparence à tous les axes ou aux deux axes X. Traits, flèches, graduations, visibilité, couleurs et épaisseurs persistants. Marges du graphique automatiques/manuelles dans Espacement. Valeurs numériques et calculs conservés ; compatibilité des anciens projets et exports de figure préservée.
- Ajout de l'éditeur de légende accessible par un clic direct sur le bouton Matplotlib, avec les onglets Cadre, Position et Texte. Cadre, fond, transparence, contour, marges séparées, retour à la ligne, positions internes et externes tenant compte des axes, coordonnées et ancre, déplacement avec blocages, police et libellés personnalisés. Affichage/masquage depuis la case dans l'éditeur. Sources et séries numériques conservées. Réglages persistants compatibles avec les anciens projets et repris dans les exports de figure.
- Correction des couleurs de légende : le thème écran ne remplace plus les couleurs choisies pour le texte, le fond et le contour. Retrait du fond blanc indépendant sous les libellés, qui partagent désormais le fond du cadre, y compris à la réouverture des anciens projets.

### English

- Import security: block network references, mapped network drives and links automatically followed from a project; limit input size, decompression and table dimensions without truncation. XML protection through defusedxml 0.7.1, included in dependencies and distribution with its license. Local sources, precision and calculations preserved.
- Documentation: explain the Windows SmartScreen warning for the unsigned executable, origin and checksum checks, launch steps and IT approval on managed computers in both language guides.
- Single vertical axis plots: restore the right frame border, black by default in exports and consistent with the axis style. Shared fix for individual experiments, overlays and means, without extra ticks or data changes.
- Release 1.0.1: include the `.atgproj` demonstration projects from `Exemple` in the archives, while excluding personal projects outside this folder.
- Legend editor: text controls use wrapping form rows to avoid horizontal overflow with the startup font.
- Read classic ATG exports named `.XLS` or without an extension while preserving their units row. Explicit extensionless import filter. Individual Δm/m₀ remains available despite unrelated heat-flow reference errors; mean Δm/m₀ and residual values use known initial masses. Changing only m₀ marks the project modified. Full-color buttons. ThermalCurve vector icon and multi-size ICO configured for Qt and PyInstaller. Renamed the French guide to README.md and updated distribution paths. Reuse identical-geometry legend placement within a single draw and locally redraw dragged legends without removing points.
- Renamed Settings > Display to Curves. Independent editing of mean TG, dTG and heat flow curves in statistics mode, with a matching standard deviation band. Ten named line styles and 25 marker choices with previews. Stacking by axis with automatic spacing, a slider and numeric input in the axis unit. Mean styles, offsets and spacing are saved in projects without changing calculations or exported data.
- Combined Customize and Spacing in Plot settings, with French/English labels. Removed legend controls and the Curves tab. Separate Grid tab for major/minor styles; independent axes, including the top and programmed-temperature axes, with appearance copying to all axes or both X axes. Persistent lines, arrows, ticks, visibility, colors and widths. Automatic/manual plot margins in Spacing. Numeric values and calculations unchanged; older projects and figure exports remain compatible.
- Added the legend editor through a direct click on the Matplotlib button, with Frame, Position and Text tabs. Frame, fill, transparency, border, separate margins, wrapping, inside and outside positions accounting for axes, coordinates and anchor, dragging with movement locks, font and custom labels. Visibility is controlled by the checkbox inside the editor. Source files and numeric series are preserved. Persistent settings remain compatible with older projects and carry over to figure exports.
- Fixed legend colors: the screen theme no longer replaces selected text, fill and border colors. Removed the independent white background under labels, which now share the frame background, including when reopening older projects.

## 1.0.1 - 2026-09-09

### Français

- Documentation du blanc : exigence explicite du même programme thermique expérimental, du même pas de temps d'acquisition et du même nombre de points que l'expérience, avec correspondance des temps point par point.
- Séparateur décimal lié à la langue de l'application (virgule en français, point en anglais), correction des masses et gaz saisis avec une virgule, adaptation des tableaux, copies et graduations. Format interne et formules chimiques préservés. Commandes du bandeau placées à gauche, titre à droite. Suppression d'états jamais relus et de règles de style visant d'anciens widgets.
- Lissage optionnel de la dTG calculée par moyenne glissante centrée, fenêtre impaire réglable en points et désactivation par défaut. Réglage enregistré par expérience, provenance dans les exports, conservation des temps, de TG et de la dTG fournie par l'appareil. Arborescence et sélecteur de courbe limités aux signaux disponibles de chaque expérience, sans flux de chaleur fictif pour les fichiers qui en sont dépourvus.
- Séparateurs de volets d'épaisseur uniforme. Adaptation des rangées de commandes et des unités dTG aux petites largeurs, listes de normalisation réductibles, largeur minimale utile et noms de fichiers longs sans débordement des panneaux.
- Programme thermique : insertion automatique des deux-points pendant la saisie des durées et de t₀ ; minutes et secondes supérieures à 59 acceptées et normalisées à la validation.
- Zones : alignement des séparateurs entre en-têtes et cellules, bordure neutre et stable au focus, champs d'édition et listes déroulantes ajustés à la cellule. Sélection et navigation au clavier conservées.

- Nom de la moyenne déplacé au-dessus du tableau des zones, sans doublon dans les lignes. Informations de contexte regroupées dans une fenêtre dédiée accessible par un bouton d'information. Couleur de ligne de base personnalisable, conservée dans les projets.
- Prise en charge des hydrates et adduits séparés par `.` ou `·` dans le calculateur stœchiométrique. Ajout du gaz par débit total × durée et composition (% molaire, ppm molaire ou ppmv), avec conditions de référence explicites et conservation des méthodes PVT. Hypothèses de maximum théorique et absence de modèle cinétique, de diffusion, de transfert ou d'équilibre affichées dans les résultats.
- Ajout des heures pour la lecture, les axes, les zones, les plages de référence, le programme thermique, les exports et les conversions dTG. Temps_s reste la base interne ; sources et correction du blanc inchangées. Interface et documentation français/anglais mises à jour.

- Zones en mode statistique : même synthèse TG/dTG/Flux de chaleur qu'en mode individuel, avec une ligne par zone pour la moyenne affichée. Pics et aires calculés sur cette moyenne avec les règles de ligne de base et d'intégration partagées ; détails statistiques conservés dans le tableau complet. Références de masse non définies et intégrales sans axe temporel signalées comme indisponibles. Séparateurs de familles plus contrastés et choix des deux couleurs d'aire dans l'apparence de chaque zone, enregistrés dans le projet avec compatibilité des anciens fichiers.

- Tableaux de zones : correction des largeurs après application des polices natives Windows, exclusion des noms d'expériences fusionnés du calcul de largeur et conservation des tailles manuelles. En-têtes de famille uniques et fusionnés, texte stable entre styles Qt, titre visible pendant le défilement horizontal continu. Précision et contenu de la copie conservés.

- Correction du texte superposé dans la colonne Blanc ; redimensionnement manuel et chemin complet en infobulle. Ajout du bouton de légende dans la barre Matplotlib, sans modification des séries. Icône crayon distincte pour Personnaliser le graphique et unités lisibles dans cet éditeur.

- Refonte du panneau Zones : onglets Définition et Résultats, ajout direct sur le graphique, édition des cellules par double-clic et Entrée, suppression du formulaire dans Réglages et des rapports textuels séparés. Synthèse conservée dans le panneau et tableau complet dans une fenêtre dédiée, première colonne Zone et regroupement par expérience. Familles TG/dTG/Flux de chaleur, dimensions adaptées au contenu, colonnes redimensionnables et copie avec en-têtes à précision complète. Affichage limité à quatre chiffres significatifs et unités lisibles sans LaTeX brut. Réglages d'apparence par zone enregistrés dans le projet. Moteurs de quantification et données sources conservés.

- Renforcement discret du contour des cases à cocher en thème clair, dans les réglages et les listes. Coches natives, états désactivés et dimensions conservés ; thème sombre inchangé.

- Interface Console (C) conservée avec des coins de 6 px pour les boutons et encadrés, sans changement de disposition ni de densité. Retrait du style Atelier (A) et du choix d'interface ; les anciennes préférences A ouvrent C. Choix Clair/Sombre maintenu.

- Distribution : inclusion explicite de XlsxWriter dans l'exécutable, contrôle bloquant à la compilation et collecte de sa licence BSD pour les archives Windows et source.

- Ajout du moteur d'écriture XlsxWriter 3.2.9 : 1,39 s contre 4,20 s avec openpyxl sur le dernier essai synthétique de 270 000 cellules (durée variable selon la charge de l'ordinateur). Valeurs, unités, styles, dimensions, trois feuilles et commentaires de provenance conservés ; repli sur openpyxl si le moteur rapide est absent ou si la provenance dépasse sa limite de commentaire. Aucun point supprimé pour accélérer l'export.

- Optimisation supplémentaire du style des cellules XLSX : environ 25 % de temps en moins par rapport à la première optimisation (médianes de trois exports synthétiques de 270 000 cellules : 5,74 s contre 4,28 s). Formats des dates et des nombres conservés.

- Correction des cases des courbes filles : un clic ne déclenche plus un second changement au relâchement de la souris. Les lignes filles TG, dTG et flux de chaleur sont affichées en retrait, cases à cocher comprises.
- Accélération des exports XLSX : dimensions calculées pendant l’écriture, mise en forme réutilisée et suppression des parcours complets des cellules. Structure à trois feuilles, valeurs, provenance et ajustement automatique conservés.

### English

- Blank documentation: explicitly requires the same experimental thermal program, acquisition time step and number of points as the experiment, with matching times point by point.
- Decimal separator follows the application language (comma in French, dot in English), with comma input fixed for calculator masses and gases and consistent tables, clipboard output and ticks. Internal formats and chemical formulas are preserved. Toolbar commands moved left and the title right. Removed unread state and style rules targeting obsolete widgets.
- Optional centered moving-average smoothing for calculated dTG, with an adjustable odd window in points and no smoothing by default. Per-experiment persistence and export provenance preserve times, TG and instrument-supplied dTG. Experiment trees and curve selectors now show only available signals, excluding heat flow when absent from the file.
- Uniform panel separator thickness. Command rows and dTG units wrap at narrow widths, normalization selectors can shrink, and a usable minimum width and long-file-name handling prevent panel overflow.
- Thermal program: automatic colon insertion while entering durations and t₀; minutes and seconds above 59 are accepted and normalized on confirmation.
- Zones: aligned separators between headers and cells, neutral focus border with stable geometry, and cell-sized editors and drop-downs. Selection and keyboard navigation are preserved.

- Moved the mean name above zone tables without duplicate rows. Context information is available in a dedicated window through an information button. Custom baseline color is saved in projects.
- Stoichiometric calculator now supports hydrates and adducts separated by `.` or `·`. Added gas input through total flow × duration and composition (molar %, molar ppm or ppmv), with explicit reference conditions and existing PVT methods retained. Results state the theoretical maximum assumption and lack of kinetics, diffusion, transfer or equilibrium modeling.
- Added hours for imports, axes, zones, reference ranges, thermal programs, exports and dTG conversions. Temps_s remains the internal time basis; sources and blank correction are unchanged. Updated French/English UI and documentation.

- Zones in statistics mode: the same TG/dTG/Heat flow summary as individual mode, with one row per zone for the displayed mean. Peaks and areas are calculated on that mean using shared baseline and integration rules; statistical details remain in the complete table. Undefined mass references and integrals without a time axis are reported as unavailable. Higher-contrast family separators and two area color controls in each zone's appearance, saved in projects with legacy compatibility.

- Zone tables: fixed column sizing after native Windows fonts are applied, excluded spanning experiment names from width measurements and preserved manual sizes. Single spanning family headers, consistent text across Qt styles and visible titles during smooth horizontal scrolling. Clipboard content and precision are preserved.

- Fixed overlapping text in the Blank column; manual resizing and full-path tooltips. Added a Matplotlib legend toggle without changing series. Distinct pencil icon for Customize plot and readable units in that editor.

- Redesigned the Zones panel with Definition and Results tabs, direct plot selection, double-click/Enter cell editing, and removal of the Settings form and separate text reports. The panel keeps its summary, while a dedicated window shows complete results, with Zone first and rows grouped by experiment. TG/dTG/Heat flow families, content-based sizing, resizable columns and full-precision copying including headers. Display uses up to four significant digits and readable units without raw LaTeX. Per-zone appearance settings are saved in the project. Quantification engines and source data are preserved.

- Subtly strengthened checkbox outlines in the light theme, in settings and lists. Native check marks, disabled states and dimensions are preserved; the dark theme is unchanged.

- Retained Console (C) with 6 px corners on buttons and panels, without changing its layout or density. Removed Workspace (A) and the interface selector; old A preferences open C. Light/Dark theme selection remains available.

- Distribution: explicitly bundle XlsxWriter in the executable, fail the build if it is missing and collect its BSD license for Windows and source archives.

- Added the XlsxWriter 3.2.9 writer: 1.39 s versus 4.20 s with openpyxl on the latest synthetic 270,000-cell benchmark (duration varies with computer load). Values, units, styles, dimensions, three sheets and provenance comments are preserved; openpyxl remains the fallback when the fast writer is missing or provenance exceeds its comment limit. No points are removed to speed up export.

- Further optimized XLSX cell styles: about 25% less time than the first optimization (medians of three synthetic exports of 270,000 cells: 5.74 s versus 4.28 s). Date and numeric formats are preserved.

- Fixed child-curve checkboxes toggling again on mouse release. TG, dTG and heat-flow child rows are now indented, including their checkboxes.
- Faster XLSX exports: dimensions collected during writing, reused cell formatting and no repeated full-cell scans. Three-sheet structure, values, provenance and automatic sizing are preserved.

## 1.0.1 - 2026-09-08

### Français

- Correction du texte superposé dans la colonne Blanc ; redimensionnement manuel et chemin complet en infobulle. Ajout du bouton de légende dans la barre Matplotlib, sans modification des séries. Icône crayon distincte pour Personnaliser le graphique et unités lisibles dans cet éditeur.

- Remplacement des groupes statistiques par le calcul automatique sur les expériences et courbes cochées ; retrait du sélecteur de domaine de l'interface.
- Liste d'expériences dépliable avec cases indépendantes TG, dTG et flux de chaleur. Réglages individuels dans Affichage : couleur, épaisseur, style, marqueurs, légende et décalage, conservés dans le projet.
- Exporter la figure déplacé dans le bandeau supérieur. Suppression du bouton Exporter les données en doublon ; Exporter conserve le classeur à trois feuilles et suit les courbes et statistiques affichées.

- Intégration de la comparaison dans le graphique principal : superposition des expériences cochées et ligne active indépendante pour les réglages individuels.
- Déplacement des statistiques dans Réglages, à côté de Zones, et des styles de courbes dans Affichage. Ajout de Retirer, Monter et Descendre dans la liste principale ; suppression de la fenêtre de comparaison séparée.
- Export principal relié au graphique commun : courbes individuelles, moyennes et écarts-types dans le classeur à trois feuilles, avec provenance et blancs partagés conservés.
- Programme thermique de l'expérience active disponible sur le graphique commun, y compris en mode statistique, lorsque cette expérience est cochée.

- Ajustement automatique des largeurs de colonnes et des hauteurs de lignes au contenu lors de l'export Excel, y compris les noms longs et les cellules contenant plusieurs lignes.
- Affichage des unités entre parenthèses à côté des noms de colonnes, dans les données traitées, les données initiales et les blancs.
- Harmonisation des exports de la fenêtre principale et de la comparaison : même présentation sur trois feuilles, nom complet du fichier au-dessus de chaque bloc, chemin sur la ligne suivante, en-têtes courts et colonne vide entre les jeux de données.
- Vérification de l'export depuis le bouton de comparaison pour quatre expériences partageant un blanc : quatre blocs corrigés sans statistiques ; uniquement la moyenne, l'écart-type et l'effectif en mode moyenne avec bande ; statistiques et quatre courbes corrigées en mode moyenne avec courbes individuelles. Les quatre blocs initiaux et le blanc unique sont conservés dans les deux dernières feuilles.

- Ajout du programme thermique par expérience : paliers, rampes, températures continues, origine modifiable et saisie des durées en hh:mm:ss. Accès depuis le bandeau principal et axe de température à droite.
- Amélioration du tableau du programme, de l'espacement des axes droits et de la lisibilité de dTG avec maintien de l'alignement des zéros lors du réglage des bornes.
- Les boutons de couleur montrent un aperçu ; le code hexadécimal reste dans l'infobulle.
- Clarification du flux de chaleur relatif à sa référence : soustraction du premier point valide ou de la moyenne d'une plage. Calcul inchangé.
- Remplacement des exports de données CSV/TSV et de leurs JSON annexes par Excel XLSX : données traitées, données initiales et blancs dans trois feuilles. Comparaisons disposées par blocs, blancs partagés dédoublonnés et statistiques conformes au mode affiché. Provenance dans les commentaires des titres.
- Inclusion du dossier `Exemple` dans les distributions source et Windows préparées par la procédure de compilation.
- Guides Markdown français et anglais actualisés : usage réservé aux exports SETARAM, ATG et couplage ATG-DSC, sans prise en charge de la DSC seule ; programme thermique et nouveaux exports documentés.

### English

- Fixed overlapping text in the Blank column; manual resizing and full-path tooltips. Added a Matplotlib legend toggle without changing series. Distinct pencil icon for Customize plot and readable units in that editor.

- Replaced statistical groups with automatic calculations on checked experiments and curves; removed the domain selector from the interface.
- Expandable experiment list with independent TG, dTG and heat-flow checkboxes. Individual Display settings for color, width, line style, markers, legend and offset are saved in the project.
- Moved Export figure to the top toolbar. Removed the duplicate Export data button; Export retains the three-sheet workbook and follows displayed curves and statistics.

- Integrated comparison into the main plot: checked experiments are overlaid while the active row independently selects the experiment to edit.
- Moved statistics into Settings beside Zones and curve styles into Display. Added Remove, Move up and Move down to the main list; removed the separate comparison window.
- Connected the main export to the shared plot: individual curves, means and standard deviations in the three-sheet workbook, preserving provenance and shared blanks.
- The active experiment's thermal program is available on the shared plot, including statistics mode, when that experiment is checked.

- Automatically fitted column widths and row heights when exporting to Excel, including long names and multiline cells.
- Units displayed in parentheses beside column names for processed data, original experiments and blanks.
- Unified main-window and comparison exports: the same three-sheet layout, full filename above each block, source path on the next row, compact headers and one empty column between datasets.
- Verified the comparison export button with four experiments sharing one blank: four corrected blocks without statistics; only mean, standard deviation and count in mean-with-band mode; statistics and four corrected curves in mean-with-individual-curves mode. All four original blocks and the single shared blank remain on the last two sheets.

- Added per-experiment thermal programs: holds, ramps, continuous temperatures, editable start time and hh:mm:ss duration entry. Accessible from the main menu bar, with a right-hand temperature axis.
- Improved program table layout, right-axis spacing and dTG readability while retaining zero alignment when adjusting bounds.
- Color buttons show swatches; hexadecimal codes remain in tooltips.
- Clarified reference-relative heat flow: subtract the first valid point or the mean of a selected range. Calculations are unchanged.
- Replaced CSV/TSV data exports and JSON sidecars with XLSX: processed data, original experiments and blanks on three sheets. Comparison blocks retain their grids, shared blanks are deduplicated and statistics follow the displayed mode. Provenance is available in title comments.
- Included `Exemple` in source and Windows distributions prepared using the build procedure.
- Updated French and English Markdown guides: SETARAM exports only, TG and coupled TG-DSC, with standalone DSC unsupported; documented thermal programs and workbook exports.
