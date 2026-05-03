#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump ZH-TW test-release.cdb into stable text files for Git diffs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

DATAS_COLUMNS = [
    "id", "ot", "alias", "setcode", "type", "atk", "def", "level", "race", "attribute", "category",
]
TEXTS_COLUMNS = ["id", "name", "desc"] + [f"str{i}" for i in range(1, 17)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def require_columns(conn: sqlite3.Connection, table: str, required: list[str]) -> None:
    found = table_columns(conn, table)
    missing = [column for column in required if column not in found]
    if missing:
        raise RuntimeError(f"{table} is missing required columns: {', '.join(missing)}")


def rows_by_id(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[int, dict[str, object]]:
    column_sql = ", ".join(f'"{column}"' for column in columns)
    rows = conn.execute(f"SELECT {column_sql} FROM {table} ORDER BY id").fetchall()
    return {int(row[0]): dict(zip(columns, row)) for row in rows}


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_schema(conn: sqlite3.Connection, path: Path) -> None:
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for object_type, name, sql in rows:
            handle.write(f"-- {object_type}: {name}\n")
            handle.write(sql.rstrip().rstrip(";") + ";\n\n")


def write_readme(path: Path, source_path: str, source_sha: str, cdb_hash: str, card_count: int) -> None:
    lines = [
        "# ZH-TW test-release.cdb Dump",
        "",
        "This branch is generated from `ZH-TW/Base Files/test-release.cdb`.",
        "It exists so database updates can be reviewed as normal Git text diffs.",
        "",
        "## Contents",
        "",
        "- `datas.csv`: raw `datas` table sorted by card id.",
        "- `texts.csv`: raw `texts` table sorted by card id.",
        "- `cards/<id>.json`: one combined card record per id for focused diffs.",
        "- `schema.sql`: SQLite schema objects.",
        "- `manifest.json`: source metadata and row counts.",
        "",
        "## Source",
        "",
        f"- Source path: `{source_path}`",
        f"- Source commit: `{source_sha or 'unknown'}`",
        f"- CDB SHA-256: `{cdb_hash}`",
        f"- Cards: `{card_count}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def dump_cdb(cdb_path: Path, out_dir: Path, source_sha: str, source_path: str) -> None:
    cdb_path = cdb_path.resolve()
    out_dir = out_dir.resolve()
    if not cdb_path.is_file():
        raise FileNotFoundError(f"CDB not found: {cdb_path}")

    ensure_clean_dir(out_dir)

    conn = sqlite3.connect(str(cdb_path))
    conn.row_factory = sqlite3.Row
    try:
        require_columns(conn, "datas", DATAS_COLUMNS)
        require_columns(conn, "texts", TEXTS_COLUMNS)

        datas = rows_by_id(conn, "datas", DATAS_COLUMNS)
        texts = rows_by_id(conn, "texts", TEXTS_COLUMNS)
        data_ids = set(datas)
        text_ids = set(texts)
        if data_ids != text_ids:
            only_datas = sorted(data_ids - text_ids)
            only_texts = sorted(text_ids - data_ids)
            raise RuntimeError(
                "datas/texts id mismatch: "
                f"only_datas={only_datas[:20]}, only_texts={only_texts[:20]}"
            )

        ids = sorted(data_ids)
        data_rows = [datas[card_id] for card_id in ids]
        text_rows = [texts[card_id] for card_id in ids]
        write_csv(out_dir / "datas.csv", data_rows, DATAS_COLUMNS)
        write_csv(out_dir / "texts.csv", text_rows, TEXTS_COLUMNS)
        write_schema(conn, out_dir / "schema.sql")

        cards_dir = out_dir / "cards"
        index_rows: list[dict[str, object]] = []
        for card_id in ids:
            card = {
                "id": card_id,
                "name": texts[card_id].get("name") or "",
                "datas": datas[card_id],
                "texts": texts[card_id],
            }
            write_json(cards_dir / f"{card_id}.json", card)
            index_rows.append({
                "id": card_id,
                "name": texts[card_id].get("name") or "",
                "type": datas[card_id].get("type"),
                "atk": datas[card_id].get("atk"),
                "def": datas[card_id].get("def"),
            })

        write_csv(out_dir / "cards-index.csv", index_rows, ["id", "name", "type", "atk", "def"])

        cdb_hash = sha256_file(cdb_path)
        manifest = {
            "source_path": source_path,
            "source_commit": source_sha or None,
            "cdb_sha256": cdb_hash,
            "tables": {
                "datas": len(data_rows),
                "texts": len(text_rows),
            },
            "cards": len(ids),
        }
        write_json(out_dir / "manifest.json", manifest)
        write_readme(out_dir / "README.md", source_path, source_sha, cdb_hash, len(ids))
        (out_dir / ".gitattributes").write_text("*.csv diff\n*.json diff\n*.sql diff\n", encoding="utf-8", newline="\n")
        (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", required=True, type=Path, help="Path to test-release.cdb")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for dump files")
    parser.add_argument("--source-sha", default="", help="Source commit sha to record in manifest")
    parser.add_argument(
        "--source-path",
        default="ZH-TW/Base Files/test-release.cdb",
        help="Repository path for the source CDB",
    )
    args = parser.parse_args()
    dump_cdb(args.cdb, args.out, args.source_sha, args.source_path)


if __name__ == "__main__":
    main()