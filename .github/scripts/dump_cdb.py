#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump a YGOPro CDB into stable text files for Git diffs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

DATAS_COLUMNS = ["id", "ot", "alias", "setcode", "type", "atk", "def", "level", "race", "attribute", "category"]
TEXTS_COLUMNS = ["id", "name", "desc"] + [f"str{i}" for i in range(1, 17)]
TEXT_VALUE_COLUMNS = ["name", "desc"] + [f"str{i}" for i in range(1, 17)]


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


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
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


def normalize_text(value: object) -> str:
    return ("" if value is None else str(value)).replace("\r\n", "\n").replace("\r", "\n")


def write_card_text(path: Path, card_id: int, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"id: {card_id}", ""]
    for field in TEXT_VALUE_COLUMNS:
        value = normalize_text(row.get(field))
        if field.startswith("str") and not value:
            continue
        lines.append(f"[{field}]")
        lines.append(value)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def text_field_rows(texts: dict[int, dict], ids: list[int]) -> list[dict]:
    rows = []
    for card_id in ids:
        card_name = normalize_text(texts[card_id].get("name"))
        for field in TEXT_VALUE_COLUMNS:
            value = normalize_text(texts[card_id].get(field))
            if field.startswith("str") and not value:
                continue
            rows.append({"id": card_id, "name": card_name, "field": field, "value": value})
    return rows


def rows_by_id(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[int, dict]:
    column_sql = ", ".join(f'"{column}"' for column in columns)
    rows = conn.execute(f"SELECT {column_sql} FROM {table} ORDER BY id").fetchall()
    return {int(row[0]): dict(zip(columns, row)) for row in rows}


def dump_cdb(cdb_path: Path, out_dir: Path, source_sha: str, source_path: str, title: str) -> None:
    cdb_path = cdb_path.resolve()
    if not cdb_path.is_file():
        raise FileNotFoundError(f"CDB not found: {cdb_path}")
    ensure_clean_dir(out_dir)
    conn = sqlite3.connect(str(cdb_path))
    try:
        datas = rows_by_id(conn, "datas", DATAS_COLUMNS)
        texts = rows_by_id(conn, "texts", TEXTS_COLUMNS)
        ids = sorted(set(datas) & set(texts))
        data_rows = [datas[card_id] for card_id in ids]
        text_rows = [texts[card_id] for card_id in ids]
        write_csv(out_dir / "datas.csv", data_rows, DATAS_COLUMNS)
        write_csv(out_dir / "texts.csv", text_rows, TEXTS_COLUMNS)
        text_fields = text_field_rows(texts, ids)
        write_csv(out_dir / "text-fields.csv", text_fields, ["id", "name", "field", "value"])
        write_csv(out_dir / "cards-index.csv", [
            {"id": card_id, "name": texts[card_id].get("name") or "", "type": datas[card_id].get("type"), "atk": datas[card_id].get("atk"), "def": datas[card_id].get("def")}
            for card_id in ids
        ], ["id", "name", "type", "atk", "def"])
        cards_dir = out_dir / "cards"
        card_texts_dir = out_dir / "card-texts"
        for card_id in ids:
            write_json(cards_dir / f"{card_id}.json", {
                "id": card_id,
                "name": texts[card_id].get("name") or "",
                "datas": datas[card_id],
                "texts": texts[card_id],
            })
            write_card_text(card_texts_dir / f"{card_id}.txt", card_id, texts[card_id])
        schema_rows = conn.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        with (out_dir / "schema.sql").open("w", encoding="utf-8", newline="\n") as handle:
            for kind, name, sql in schema_rows:
                handle.write(f"-- {kind}: {name}\n{sql.rstrip().rstrip(';')};\n\n")
        cdb_hash = sha256_file(cdb_path)
        write_json(out_dir / "manifest.json", {
            "title": title,
            "source_path": source_path,
            "source_commit": source_sha or None,
            "cdb_sha256": cdb_hash,
            "cards": len(ids),
            "tables": {"datas": len(data_rows), "texts": len(text_rows)},
            "text_fields": len(text_fields),
        })
        (out_dir / "README.md").write_text(
            f"# {title}\n\nGenerated from `{source_path}` so database updates can be reviewed as text diffs.\n\nCards: `{len(ids)}`\n\n## Contents\n\n- `texts.csv`: raw CDB `texts` table, including `name`, `desc`, and `str1`-`str16`.\n- `text-fields.csv`: one row per dumped CDB text field for easier additions/removals.\n- `card-texts/<id>.txt`: one readable text dump per card for focused text diffs.\n- `datas.csv`: raw CDB `datas` table.\n- `cards/<id>.json`: combined card data and text record.\n\nCDB SHA-256: `{cdb_hash}`\n",
            encoding="utf-8",
            newline="\n",
        )
        (out_dir / ".gitattributes").write_text("*.csv diff\n*.json diff\n*.sql diff\n*.txt diff\n", encoding="utf-8", newline="\n")
        (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdb", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--source-path", default="")
    parser.add_argument("--title", default="CDB Dump")
    args = parser.parse_args()
    dump_cdb(args.cdb, args.out, args.source_sha, args.source_path, args.title)


if __name__ == "__main__":
    main()
