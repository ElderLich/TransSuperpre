# ZH-TW test-release.cdb Dump

This branch is generated from `ZH-TW/Base Files/test-release.cdb`.
It exists so database updates can be reviewed as normal Git text diffs.

## Contents

- `datas.csv`: raw `datas` table sorted by card id.
- `texts.csv`: raw `texts` table sorted by card id.
- `text-fields.csv`: one row per dumped CDB text field for easier additions/removals.
- `card-texts/<id>.txt`: one readable text dump per card for focused text diffs.
- `cards/<id>.json`: one combined card record per id for focused diffs.
- `schema.sql`: SQLite schema objects.
- `manifest.json`: source metadata and row counts.

## Source

- Source path: `ZH-TW/Base Files/test-release.cdb`
- Source commit: `0f15accc6a6e90e13c0849e7a9f4c020c86d690f`
- CDB SHA-256: `0295f3d77d1cc501404bccb07aac8d84fc5c60f3c8efa15dcd0d43986f24e062`
- Cards: `90`
