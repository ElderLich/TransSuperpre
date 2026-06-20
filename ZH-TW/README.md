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
- Source commit: `dd6cb23d6ee0368a302e581210619d8ed96e8900`
- CDB SHA-256: `bb287bbb9b50e7f10db74c30670f28ba143ca2079a0ba6150ea409e6be9643ab`
- Cards: `90`
