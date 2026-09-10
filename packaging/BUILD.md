# Compiler ThermalCurve / Building ThermalCurve

[Français](#français) | [English](#english)

## Français

Cette procédure concerne le projet source sur Windows x64. Elle utilise les
scripts existants et ne modifie pas une Release déjà publiée. Les commandes sont
à lancer dans PowerShell, à la racine du projet, où se trouve `run_qt.py`.

### 1. Préparer l'environnement

Sur ton ordinateur actuel, conserve la `.venv` existante. Vérifie les outils :

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m PyInstaller --version
.venv\Scripts\python.exe -m pip check
```

La version 1.0.0 a été construite avec Python **3.14.6 x64** et PyInstaller
**6.21.0**. `requirements.txt` fixe les sept dépendances directes de l'application,
dont XlsxWriter 3.2.9 pour l'export rapide depuis la version 1.0.1.
Le fichier `.spec` inclut XlsxWriter et refuse la compilation si son module
d'écriture est absent. La collecte des notices inclut aussi sa licence BSD.
Les dépendances transitives ne sont pas toutes verrouillées : une nouvelle
installation n'est donc pas nécessairement identique à l'environnement original.

Sur un autre ordinateur, installer Python 3.14.6 x64, puis exécuter ces commandes
une seule fois dans une copie des sources sans `.venv` :

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -c requirements.txt "pyinstaller==6.21.0" -e ".[dev]"
.venv\Scripts\python.exe -m pip check
```

Arrêter si une commande échoue. L'activation PowerShell de `.venv` n'est pas
nécessaire : chaque commande utilise directement son interpréteur.

### 2. Choisir et renseigner la nouvelle version

Par exemple, pour passer à **1.1.0**, modifier uniquement les mentions suivantes :

| Fichier | Valeurs à mettre à jour |
| --- | --- |
| `atg_dsc_corrector/__init__.py` | `__version__ = "1.1.0"` |
| `pyproject.toml` | `version = "1.1.0"` dans `[project]` |
| `atg_dsc_corrector_qt.spec` | `filevers=(1, 1, 0, 0)`, `prodvers=(1, 1, 0, 0)`, puis `FileVersion` et `ProductVersion` à `"1.1.0"` |
| `README.md` et `README_EN.md` | Version du titre et instructions affectées par les changements |

Ces valeurs ne sont pas synchronisées automatiquement. Le nom des ZIP est lu
dans `pyproject.toml`. Ne pas faire de remplacement global de `1.0.0` : la licence
**PolyForm Noncommercial 1.0.0** et les références historiques gardent leur numéro.
Mettre à jour le copyright seulement lorsque c'est approprié.

### 3. Valider les sources

L'icône est définie dans `atg_dsc_corrector/resources/thermalcurve.svg`.
Après modification de ce dessin, régénérer l'ICO multi-tailles avec
`.venv\Scripts\python.exe packaging/generate_icon.py`. Le fichier `.spec` l'incorpore
à l'exécutable et aux ressources Qt. Les dimensions sont 16, 24, 32, 48, 64, 128 et 256 px.

Dans le dépôt de travail complet, lancer les tests après les modifications :

```powershell
.venv\Scripts\python.exe -m pytest
```

Attendre la fin et un code de sortie nul. Corriger les échecs avant la compilation.
Le ZIP source publié pour 1.0.0 exclut le dossier `tests` : il permet de compiler,
mais ne suffit pas à reproduire cette validation. Garder le dépôt de travail
complet pour préparer les versions suivantes.

### 4. Préparer les notices et sources tierces

Avec les mêmes dépendances, conserver le dossier `licenses` et les **sept archives**
originales dans `.tmp/third-party-sources`. Elles sont déjà présentes dans le dépôt
de travail actuel. Sur une autre machine, télécharger
`ThermalCurve-1.0.0-third-party-sources.zip` depuis la
[Release 1.0.0](https://github.com/Valent1L/ThermalCurve/releases/tag/v1.0.0),
l'extraire à part, puis copier les sept fichiers de son dossier
`third-party-sources` directement dans `.tmp/third-party-sources`.
Les chemins et empreintes attendus figurent dans `licenses/SOURCE_ARCHIVES_SHA256.txt`.

```powershell
.venv\Scripts\python.exe packaging/prepare_licenses.py
```

Ce script collecte les notices locales ; il ne télécharge pas les archives et
n'installe aucune dépendance. Si les versions des dépendances changent, actualiser
d'abord leurs sources et notices, ainsi que les versions attendues dans
`packaging/prepare_licenses.py`. Revalider aussi le hook Qt et la distribution.
Les archives et notices de 1.0.0 ne doivent pas être réutilisées comme si elles
décrivaient de nouvelles versions des bibliothèques.

### 5. Construire le dossier Windows

Exécuter ce bloc dans une même session PowerShell. Il lit la version du projet,
refuse de remplacer un dossier de distribution existant et restaure le `PATH`
après la compilation. Le `PATH` minimal évite de collecter des DLL d'autres logiciels.

```powershell
$releaseVersion = & .venv\Scripts\python.exe -c "import pathlib,tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { throw 'Lecture de version impossible / Cannot read version' }
$releaseFolder = "dist/ThermalCurve-$releaseVersion-windows-x64"
if (Test-Path -LiteralPath $releaseFolder) { throw 'Dossier deja present / Output folder already exists' }
$previousPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & .venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --distpath $releaseFolder --workpath "build/thermalcurve-$releaseVersion" atg_dsc_corrector_qt.spec
    if ($LASTEXITCODE -ne 0) { throw 'Compilation echouee / Build failed' }
} finally {
    $env:PATH = $previousPath
}
$bundle = Join-Path $releaseFolder 'ThermalCurve'
Copy-Item -LiteralPath 'README.md','README_EN.md','changelog.md','LICENSE.txt','THIRD_PARTY_NOTICES.txt' -Destination $bundle -ErrorAction Stop
Copy-Item -LiteralPath 'licenses','Exemple' -Destination $bundle -Recurse -ErrorAction Stop
```

Pour 1.1.0, le programme est dans
`dist/ThermalCurve-1.1.0-windows-x64/ThermalCurve/ThermalCurve.exe`.
Le fichier `.spec` conserve les ressources et le mode dossier autonome ; ne pas
le remplacer par une commande générique `--onefile` sur `run_qt.py`.
La copie des notices et des guides après compilation est nécessaire : le `.spec`
ne les ajoute pas au dossier racine du binaire.

### 6. Vérifier le programme compilé

Ouvrir l'exécutable depuis l'Explorateur Windows et vérifier :

- le nom et la nouvelle version dans « À propos », en français et en anglais ;
- le chargement d'un exemple synthétique ou d'une copie de données autorisée,
  le traitement, la comparaison et les exports XLSX et PNG/SVG/PDF ;
- la sauvegarde et la réouverture d'un nouveau projet de test ;
- les calculs stœchiométriques et le tableau périodique ;
- le lancement après copie du dossier **complet** dans un autre emplacement.

Vérifier en priorité les fonctionnalités qui ont changé. Ne pas écraser de données
expérimentales pendant ces essais. Un build réussi ne prouve pas à lui seul que
tous les parcours fonctionnent. Fermer le programme avant l'archivage.

### 7. Créer et publier les archives

Une fois les contrôles réussis :

```powershell
.venv\Scripts\python.exe packaging/make_archives.py
if ($LASTEXITCODE -ne 0) { throw 'Archivage echoue / Archiving failed' }
```

Le script vérifie les empreintes des archives tierces, crée les trois ZIP, relit
leur intégrité et écrit `dist/SHA256SUMS.txt`. Pour la version de l'exemple :

- `ThermalCurve-1.1.0-windows-x64.zip` : programme autonome pour les utilisateurs ;
- `ThermalCurve-1.1.0-source.zip` : sources propres, guides et procédure de compilation ;
- `ThermalCurve-1.1.0-third-party-sources.zip` : sources tierces ;
- `SHA256SUMS.txt` : empreintes des trois ZIP.

Une nouvelle exécution remplace les ZIP du même numéro et `SHA256SUMS.txt`.
Conserver les livrables de chaque version dans leur propre dossier d'archivage.
Extraire le nouveau ZIP Windows ailleurs et tester son exécutable avant publication.

Sur GitHub, publier les sources propres, créer un tag correspondant (par exemple
`v1.1.0`), puis une nouvelle Release à partir de ce tag. Joindre les trois ZIP et
`SHA256SUMS.txt`, et décrire les changements en français et en anglais. Conserver
la Release 1.0.0. L'historique du dépôt de travail local contient des données et
configurations privées : utiliser la copie de publication propre, pas un push
global de cet historique. Sur cet ordinateur, cette copie se trouve dans
`.tmp/github-publication/checkout` ; ce dossier temporaire n'est pas une sauvegarde.

## English

Run these steps in PowerShell at the source project root on Windows x64, where
`run_qt.py` is located. They use the existing tools to prepare a new release.

### 1. Prepare the environment

Keep the existing `.venv` on the current computer. Check Python, PyInstaller and
installed dependencies with the first command block in the French section.
Version 1.0.0 was built with **Python 3.14.6 x64** and **PyInstaller 6.21.0**.
`requirements.txt` pins the seven direct application dependencies, including
XlsxWriter 3.2.9 for fast exports since version 1.0.1; transitive
dependencies are not fully pinned, so a fresh installation may differ.
The `.spec` includes XlsxWriter and fails the build if its workbook module is
missing. Notice collection also includes its BSD license.

On another computer, install Python 3.14.6 x64, then run:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -c requirements.txt "pyinstaller==6.21.0" -e ".[dev]"
.venv\Scripts\python.exe -m pip check
```

Stop on any failure. PowerShell activation is unnecessary because each command
uses the virtual environment's interpreter directly.

### 2. Set the new version

For **1.1.0**, update `__version__` in `atg_dsc_corrector/__init__.py`, the project
`version` in `pyproject.toml`, both Windows version strings in
`atg_dsc_corrector_qt.spec`, and its `filevers`/`prodvers` tuples to `(1, 1, 0, 0)`.
Update both Markdown README titles and any changed user instructions. These values
are not synchronized automatically; ZIP names use `pyproject.toml`. Do not globally
replace `1.0.0`: the PolyForm Noncommercial license version and historical references
retain their numbers. Update copyright only when appropriate.

### 3. Validate the sources

```powershell
.venv\Scripts\python.exe -m pytest
```

Wait for completion and a zero exit code; fix failures before building. The published
1.0.0 source ZIP excludes `tests`. It supports building but cannot reproduce the
full validation suite; retain the complete working repository for future releases.

### 4. Prepare third-party notices and sources

With unchanged dependencies, retain `licenses` and the seven original archives
directly inside `.tmp/third-party-sources`. On a fresh machine, obtain the
third-party source ZIP from the [1.0.0 Release](https://github.com/Valent1L/ThermalCurve/releases/tag/v1.0.0),
extract it separately, and copy the seven files from its `third-party-sources`
folder to that location. Expected names and hashes are recorded in
`licenses/SOURCE_ARCHIVES_SHA256.txt`.

```powershell
.venv\Scripts\python.exe packaging/prepare_licenses.py
```

This collects local notices without downloads or dependency installation. If
dependency versions change, update corresponding sources, notices and the expected
versions in this script first. Revalidate the Qt hook and the package. Do not assume
the 1.0.0 notices describe newer dependency versions.

### 5. Build the Windows folder

Run the complete PowerShell block in French step 5 unchanged. It reads the project
version, refuses an existing output folder, temporarily restricts `PATH` to Windows
system directories, runs the existing `.spec`, restores `PATH`, then copies both
Markdown guides, dated changelog, example folder and all license notices alongside the executable. These copies are
necessary because the `.spec` does not place them at the binary folder root.

For 1.1.0, the result is
`dist/ThermalCurve-1.1.0-windows-x64/ThermalCurve/ThermalCurve.exe`.
Keep the `.spec` and its standalone folder mode rather than replacing the command
with a generic `--onefile` invocation on `run_qt.py`.

### 6. Check the executable

Check About and the new version in both languages; import, processing, comparison,
XLSX and PNG/SVG/PDF exports; saving and reopening a new test project;
stoichiometry and the periodic table. Prioritize changed functionality. Use synthetic
examples or authorized copies and never overwrite experimental files. Copy the
entire application folder elsewhere and verify startup. Build success alone does
not validate every workflow. Close the executable before archiving.

### 7. Archive and publish

```powershell
.venv\Scripts\python.exe packaging/make_archives.py
if ($LASTEXITCODE -ne 0) { throw 'Archiving failed' }
```

This validates upstream archive hashes, creates and checks the three ZIP files,
and writes `dist/SHA256SUMS.txt`. The Windows ZIP is for users, the source ZIP
contains clean sources and documentation, and the third-party ZIP contains upstream
sources. Running the script again replaces ZIPs with the same version number and
the checksum file; preserve each release's artifacts separately. Extract the Windows
ZIP elsewhere and test it before publishing.

Publish the clean sources to GitHub, create a matching tag such as `v1.1.0`, and
create a new Release from that tag with all three ZIPs, the checksum file and
bilingual release notes. Keep the existing 1.0.0 Release. The local working history
contains private configuration and data: use the clean publication checkout, not
a push of that history. On the current computer the publication checkout is
`.tmp/github-publication/checkout`; this temporary directory is not a backup.

## Références / References

- [PyInstaller: using spec files](https://pyinstaller.org/en/stable/spec-files.html)
- [PyInstaller: command-line options](https://pyinstaller.org/en/stable/usage.html)
- [Configuration du build / Build configuration](../atg_dsc_corrector_qt.spec)
- [Création des archives / Archive creation](make_archives.py)
- [Collecte des notices / Notice collection](prepare_licenses.py)
