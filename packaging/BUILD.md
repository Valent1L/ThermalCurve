# Préparer la distribution des sources / Prepare the source distribution

## Français

Depuis le 10 septembre 2026, la distribution 1.0.1 est préparée uniquement sous
forme de sources Python. L'exécutable signalé par Defender a été soumis à Microsoft
et son analyse est en attente. Le processus ci-dessous ne compile pas d'exécutable
et ne prépare pas d'archive Windows avec Python embarqué.

### Préparer et vérifier

Travailler à la racine du projet avec l'environnement de développement déjà
installé. Pour l'installation utilisateur et le lancement, suivre
[README.md](../README.md). Aucun PyInstaller ni téléchargement de sources tierces
n'est nécessaire à la création de ce ZIP.

La version et le nom des archives sont lus dans `pyproject.toml`. Avant une
nouvelle version, tenir aussi à jour `atg_dsc_corrector/__init__.py`, les deux
README et `changelog.md`. Conserver les exemples autorisés et les fichiers
`atg_dsc_corrector/resources/thermalcurve.ico` et `thermalcurve.svg`.

Depuis le dépôt de développement complet, valider la sélection des fichiers :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_archives.py
```

Ce test utilise des fichiers synthétiques isolés. Il vérifie la conservation des
sources, exemples et licences, l'exclusion des binaires et projets personnels,
ainsi que l'empreinte de l'archive. Le dossier `tests` n'est pas livré dans le ZIP.

### Créer l'archive

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
la release 1.0.1 : retirer l'ancien ZIP `windows-x64` des fichiers téléchargeables,
puis remplacer le ZIP de sources et `SHA256SUMS.txt` par ceux du nouveau dossier.
Si un `.exe` est proposé séparément, le retirer également. Indiquer dans la
description que Python doit être installé et renvoyer vers les README actualisés.
Les sources tierces d'anciennes distributions peuvent rester disponibles pour
conserver leur provenance.

Les fichiers visibles sur la page principale du dépôt doivent être mis à jour
séparément dans le dépôt public, notamment les deux README. Une modification des
pièces jointes de la release ne modifie pas ces fichiers ni le code associé au tag.
Ne pas pousser l'historique du dépôt de travail contenant des données privées :
utiliser le dépôt public préparé pour la publication et vérifier chaque fichier.
Ce script ne crée ni commit, ni tag, ni publication GitHub.

## English

As of September 10, 2026, release 1.0.1 is prepared as Python sources only. The
executable detected by Defender has been submitted to Microsoft and analysis is
pending. This procedure does not build an executable or a Windows runtime bundle.

### Prepare and check

Work at the project root with the existing development environment. User
installation and startup are documented in [README_EN.md](../README_EN.md).
Neither PyInstaller nor third-party source downloads are required to create this ZIP.

The version and archive names come from `pyproject.toml`. For a new version, also
update `atg_dsc_corrector/__init__.py`, both READMEs and `changelog.md`. Preserve
the authorized examples and `atg_dsc_corrector/resources/thermalcurve.ico` and
`thermalcurve.svg`.

From the full development checkout, validate file selection:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_archives.py
```

The test uses isolated synthetic files to check preservation of sources, examples
and licenses, exclusion of binaries and private projects, and the archive checksum.
The `tests` directory is not distributed in the ZIP.

### Create the archive

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
1.0.1: remove the old `windows-x64` ZIP from the downloadable assets, then replace
the source ZIP and `SHA256SUMS.txt` with the new files. Remove any separately
published `.exe` as well. Explain in the description that Python must be installed
and link to the updated READMEs. Third-party sources for previous distributions
may remain available to preserve their provenance.

Files shown on the repository's main page, especially both READMEs, need to be
updated separately in the public repository. Changing release attachments does
not update these files or the code associated with the tag. Do not push the working
repository's history containing private data: use the checkout prepared for public
release and review each file. This script creates no commit, tag or GitHub publication.
