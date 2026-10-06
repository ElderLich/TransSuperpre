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
- Source commit: `8864deb7239d22f08915dd3d7f3f1be0521db61e`
- CDB SHA-256: `84f8b5daf1368eabc689c05f5e692b08d0e0071f6cae73bd0cfe8b77a06f4dab`
- Cards: `96`
