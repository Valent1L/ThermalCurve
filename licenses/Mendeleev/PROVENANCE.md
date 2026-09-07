# Provenance des données Mendeleev

- Dépôt source : `lmmentel/mendeleev-data`.
- Version publiée : `v0.20.0`.
- Commit immuable : `310fcad9ddf3191781abe735e61f6cd19ce8a5ee`.
- Release : https://github.com/lmmentel/mendeleev-data/releases/tag/v0.20.0
- Date d'acquisition : 2026-09-04.
- Licence redistribuée : MIT, dans `LICENSE` sans modification.

## Fichiers acquis

| Fichier | URL source exacte | Taille (octets) | SHA-256 |
| --- | --- | ---: | --- |
| `elements.json` | https://raw.githubusercontent.com/lmmentel/mendeleev-data/310fcad9ddf3191781abe735e61f6cd19ce8a5ee/data/json/elements.json | 441018 | `c1143e011bb63b7c533666cdf8a68cc0b9ad9f549fa6e58412fc0e08f4c8839d` |
| `LICENSE` | https://raw.githubusercontent.com/lmmentel/mendeleev-data/310fcad9ddf3191781abe735e61f6cd19ce8a5ee/LICENSE | 1070 | `bcbc87d5f4ce66074a3a51d84a44df0de94d0f1a4cc794e4c17bc497b226e5eb` |

## Contrôles à l'acquisition

- Export Mendeleev lu sans modifier le fichier. Malgré son extension JSON, il
  contient des virgules terminales et quelques chaînes entre apostrophes. Le
  chargeur standard-library le lit comme un littéral de données après
  normalisation en mémoire des seuls littéraux `null`, `true` et `false`.
- Enregistrements : 118.
- Numéros atomiques uniques : 118, de 1 à 118.
- Symboles uniques : 118.
- Champs candidats relevés : `atomic_number`, `symbol`, `name`, `atomic_weight`,
  `group_id`, `period`, `block`, `electronic_configuration`, `is_radioactive`
  et `series_id`.

## Règle d'autorité

Ces données enrichissent uniquement le tableau de consultation J24. Les noms
français, masses affichées et masses de calcul restent ceux de
`atg_dsc_corrector.atomic_data` (CIAAW/IUPAC, J18). Toute jointure future doit
exiger le même numéro atomique et le même symbole sensible à la casse.

Le dépôt de données publié acquis est `v0.20.0`. Il ne doit pas être présenté
comme un instantané `mendeleev v1.2.0` sans preuve publiée de correspondance.
La version exacte ci-dessus doit être affichée dans toute interface qui expose
la provenance de l'enrichissement.
