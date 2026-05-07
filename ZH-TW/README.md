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
- Source commit: `45ac9b3377a7e37f0395f729c427e2cdfe48642f`
- CDB SHA-256: `8d4f4174c1d8352865cc8f4a24d8561b5f3466d65e31f770622609fcfbf9acb6`
- Cards: `131`
