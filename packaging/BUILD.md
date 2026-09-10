# Préparer les distributions / Prepare the distributions

## Français

Deux formats sont proposés : les sources Python et un ZIP portable Windows x64
avec le Python officiel embarqué. Aucun `ThermalCurve.exe` n'est compilé ;
le portable utilise `Lancer_ThermalCurve.cmd`. L'ancien exécutable reste bloqué
par Windows Defender et pourra être proposé à nouveau si le problème est résolu.

### Préparer et vérifier

Travailler à la racine du projet avec l'environnement de développement déjà
installé. Pour l'installation utilisateur et le lancement, suivre
[README.md](../README.md). PyInstaller n'est nécessaire pour aucun de ces formats.
Le ZIP de sources seul ne nécessite aucun téléchargement de sources tierces.

La version et le nom des archives sont lus dans `pyproject.toml`. Avant une
nouvelle version, tenir aussi à jour `atg_dsc_corrector/__init__.py`, les deux
README et `changelog.md`. Conserver les exemples autorisés et les fichiers
`atg_dsc_corrector/resources/thermalcurve.ico` et `thermalcurve.svg`.

Depuis le dépôt de développement complet, valider la sélection des fichiers :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_archives.py
```

Ces tests utilisent des fichiers synthétiques isolés. Ils vérifient la séparation
des sources et du runtime, les empreintes et l'exclusion des projets personnels
et de `ThermalCurve.exe`. Le dossier `tests` n'est pas livré dans le ZIP.

### Préparer la version portable

Télécharger le [Python 3.14.6 embarqué officiel, 64 bits](https://www.python.org/downloads/release/python-3146/)
dans `.tmp/python-3.14.6-embed-amd64.zip`. Le script vérifie son SHA-256 officiel
avant extraction : `df901e84a896ff1ee720ad03377e0c8d8c2244fda79808aeeaff6316df1cb75c`.

```powershell
.\.venv\Scripts\python.exe packaging/prepare_portable.py .tmp/python-3.14.6-embed-amd64.zip .tmp/portable-python-1.0.1/python
.\.venv\Scripts\python.exe packaging/make_archives.py --portable-runtime .tmp/portable-python-1.0.1/python
```

La préparation exige un dossier de runtime neuf. Elle copie les dépendances de
l'environnement de développement validé, sans modifier `.venv`, et conserve
les modules Qt Core, Gui, Widgets, Network et Svg utilisés par l'application.
Les versions sont consignées dans `python/PORTABLE_RUNTIME.json`. Les chemins
Python sont limités au portable ; le lanceur ignore les installations externes.

Les archives tierces déjà référencées dans `licenses/SOURCE_ARCHIVES_SHA256.txt`
doivent être disponibles dans `.tmp/third-party-sources` avec les mêmes empreintes.
Elles sont redistribuées séparément pour accompagner les bibliothèques incluses.

Le dossier **`dist/ThermalCurve-1.0.1-portable/`** contient les fichiers à publier :

- `ThermalCurve-1.0.1-windows-x64-portable.zip` ;
- `ThermalCurve-1.0.1-source.zip` ;
- `ThermalCurve-1.0.1-third-party-sources.zip` ;
- `SHA256SUMS.txt`, avec les empreintes des trois ZIP.

Extraire le portable dans un autre emplacement et vérifier le lanceur, les deux
exemples, les exports et l'absence de recours au Python de développement. Contrôler
le dossier et le ZIP avec Defender avant publication. Un contrôle local sans
détection ne garantit pas l'absence de blocage sur tous les postes.

### Créer uniquement l'archive de sources

```powershell
.\.venv\Scripts\python.exe packaging/make_archives.py
```

Pour la version 1.0.1, le dossier à publier est
`dist/ThermalCurve-1.0.1-sources/`. Il contient uniquement :

- `ThermalCurve-1.0.1-source.zip` ;
- `SHA256SUMS.txt`, avec l'empreinte SHA-256 de ce ZIP.

Le ZIP contient le code, `run_qt.py`, les dépendances déclarées, les guides,
le changelog, `Exemple`, les ressources dont l'icône, les licences et les scripts
de préparation. Le fichier `.spec` reste disponible pour les développeurs ;
il n'est pas exécuté par cette procédure.

Les exécutables et bibliothèques compilées (`.exe`, `.dll`, `.pyd`, `.so`, `.dylib`),
les caches, les environnements locaux et les projets personnels sont exclus.
Seuls les projets `.atgproj` du dossier `Exemple` sont inclus. La liste des fichiers
de premier niveau est explicite : ne pas y ajouter de fichiers privés.

Le script refuse un dossier de publication contenant d'autres fichiers. Les
anciennes archives et dossiers compilés ailleurs dans `dist` restent inchangés.
Ne pas les mélanger au nouveau dossier. Les notices et références des sources
tierces restent dans le ZIP ; les bibliothèques sont installées par `pip`, et
aucune nouvelle archive de leurs sources n'est produite.

Après création, contrôler le contenu du ZIP, son extraction et le lancement depuis
les sources extraites. Vérifier l'empreinte avec :

```powershell
Get-FileHash .\dist\ThermalCurve-1.0.1-sources\ThermalCurve-1.0.1-source.zip -Algorithm SHA256
```

### Mettre à jour GitHub manuellement

Dans la page [Releases](https://github.com/Valent1L/ThermalCurve/releases), modifier
la release 1.0.1 : retirer l'ancien ZIP `windows-x64` avec `ThermalCurve.exe`, puis
ajouter les quatre fichiers du dossier `dist/ThermalCurve-1.0.1-portable/`.
Remplacer les pièces jointes de même nom. Utiliser la description de
`RELEASE_1.0.1.md`, qui distingue le portable sans installation du ZIP de sources.

Les fichiers visibles sur la page principale du dépôt doivent être mis à jour
séparément dans le dépôt public, notamment les deux README. Une modification des
pièces jointes de la release ne modifie pas ces fichiers ni le code associé au tag.
Ne pas pousser l'historique du dépôt de travail contenant des données privées :
utiliser le dépôt public préparé pour la publication et vérifier chaque fichier.
Ce script ne crée ni commit, ni tag, ni publication GitHub.

## English

Two formats are provided: Python sources and a portable Windows x64 ZIP with
official embedded Python. No `ThermalCurve.exe` is built; the portable uses
`Lancer_ThermalCurve.cmd`. The previous executable remains blocked by Windows
Defender and may be offered again if the issue is resolved.

### Prepare and check

Work at the project root with the existing development environment. User
installation and startup are documented in [README_EN.md](../README_EN.md).
Neither format requires PyInstaller. The source-only ZIP requires no third-party
source downloads.

The version and archive names come from `pyproject.toml`. For a new version, also
update `atg_dsc_corrector/__init__.py`, both READMEs and `changelog.md`. Preserve
the authorized examples and `atg_dsc_corrector/resources/thermalcurve.ico` and
`thermalcurve.svg`.

From the full development checkout, validate file selection:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_archives.py
```

The tests use isolated synthetic files to check source/runtime separation,
checksums and exclusion of private projects and `ThermalCurve.exe`.
The `tests` directory is not distributed in the ZIP.

### Prepare the portable version

Download [official embedded Python 3.14.6, 64-bit](https://www.python.org/downloads/release/python-3146/)
to `.tmp/python-3.14.6-embed-amd64.zip`. The script checks its official SHA-256
before extraction: `df901e84a896ff1ee720ad03377e0c8d8c2244fda79808aeeaff6316df1cb75c`.

```powershell
.\.venv\Scripts\python.exe packaging/prepare_portable.py .tmp/python-3.14.6-embed-amd64.zip .tmp/portable-python-1.0.1/python
.\.venv\Scripts\python.exe packaging/make_archives.py --portable-runtime .tmp/portable-python-1.0.1/python
```

Preparation requires a new runtime directory. It copies dependencies from the
validated development environment without modifying `.venv`, retaining the Qt
Core, Gui, Widgets, Network and Svg modules used by the application. Versions
are recorded in `python/PORTABLE_RUNTIME.json`. Python search paths are limited
to the portable folder; the launcher ignores external installations.

Third-party archives listed in `licenses/SOURCE_ARCHIVES_SHA256.txt` must be
available in `.tmp/third-party-sources` with matching checksums. They are distributed
separately to accompany the bundled libraries.

Publish the four files in **`dist/ThermalCurve-1.0.1-portable/`**:

- `ThermalCurve-1.0.1-windows-x64-portable.zip`;
- `ThermalCurve-1.0.1-source.zip`;
- `ThermalCurve-1.0.1-third-party-sources.zip`;
- `SHA256SUMS.txt`, containing the checksums of all three ZIPs.

Extract the portable elsewhere and check the launcher, both examples, exports
and independence from development Python. Scan the folder and ZIP with Defender
before publication. A local scan without detections does not guarantee that
every computer will allow the application to run.

### Create only the source archive

```powershell
.\.venv\Scripts\python.exe packaging/make_archives.py
```

For version 1.0.1, publish only the contents of
`dist/ThermalCurve-1.0.1-sources/`:

- `ThermalCurve-1.0.1-source.zip`;
- `SHA256SUMS.txt`, containing the ZIP's SHA-256 checksum.

The ZIP contains the code, `run_qt.py`, dependency declarations, guides, changelog,
`Exemple`, resources including the icon, licenses and preparation scripts. The
`.spec` file remains available to developers; this procedure does not run it.

Executables and compiled libraries (`.exe`, `.dll`, `.pyd`, `.so`, `.dylib`), caches,
local environments and private projects are excluded. Only `.atgproj` files under
`Exemple` are included. Top-level files are explicitly listed; do not add private files.

The script rejects a publication folder containing other files. Earlier archives
and compiled folders elsewhere in `dist` are preserved. Keep them separate from the
new folder. Third-party notices and source references remain in the ZIP; libraries
are installed with `pip`, and no new third-party source archive is generated.

After creation, check ZIP contents, extraction and startup from the extracted
sources. Verify the checksum with:

```powershell
Get-FileHash .\dist\ThermalCurve-1.0.1-sources\ThermalCurve-1.0.1-source.zip -Algorithm SHA256
```

### Update GitHub manually

On the [Releases page](https://github.com/Valent1L/ThermalCurve/releases), edit release
1.0.1: remove the old `windows-x64` ZIP containing `ThermalCurve.exe`, then upload
the four files from `dist/ThermalCurve-1.0.1-portable/`. Replace existing attachments
with the same name. Use `RELEASE_1.0.1.md`, which distinguishes the portable version
without installation from the source ZIP.

Files shown on the repository's main page, especially both READMEs, need to be
updated separately in the public repository. Changing release attachments does
not update these files or the code associated with the tag. Do not push the working
repository's history containing private data: use the checkout prepared for public
release and review each file. This script creates no commit, tag or GitHub publication.
