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
- Source commit: `7263a1f34869c64c779da4164fa0840f0aaf2caa`
- CDB SHA-256: `fda52a999059a39454ad673435667c558875330026c0d0c2df08ba9d04f16a58`
- Cards: `153`
