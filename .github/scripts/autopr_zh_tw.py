#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the ZH-TW Super-Pre package using the same sources as the TW AutoPR flow.

Source mapping:
- salix5/CardEditor expansions/beta.cdb -> test-release.cdb
- salix5/CardEditor expansions/pre-strings.conf -> test-strings.conf
- test-update.cdb is extracted from the downloaded super-pre ypk and translated with
  salix5/cdb snapshot cards.cdb.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(os.environ.get("TW_AUTOPR_OUTPUT_DIR", ROOT / "ZH-TW")).resolve()
BASE_FILES_DIR = Path(os.environ.get("TW_AUTOPR_BASE_FILES_DIR", OUTPUT_DIR / "Base Files")).resolve()
CARDEDITOR_EXPANSIONS_DIR = Path(
    os.environ.get("TW_AUTOPR_CARDEDITOR_EXPANSIONS_DIR", ROOT / "_cardeditor" / "expansions")
).resolve()
YPK_URL = os.environ.get(
    "TW_AUTOPR_YPK_URL",
    "https://cdn02.moecube.com:444/ygopro-super-pre/archive/ygopro-super-pre.ypk",
)
JSON_URL = os.environ.get(
    "TW_AUTOPR_JSON_URL",
    "https://cdn02.moecube.com:444/ygopro-super-pre/data/test-release.json",
)
CARDS_CDB_URL = os.environ.get(
    "TW_AUTOPR_CARDS_CDB_URL",
    "https://github.com/salix5/cdb/releases/download/snapshot/cards.cdb",
)
REPLACEMENT_MAP = {
    "/神": "/Divine",
    "/暗": "/Dark",
    "/光": "/Light",
    "/风": "/Wind",
    "/風": "/Wind",
    "/地": "/Earth",
    "/水": "/Water",
    "/炎": "/Fire",
    "[怪兽": "[Monster",
    "[怪獸": "[Monster",
    "[魔法": "[Spell",
    "[陷阱": "[Trap",
    "幻想魔": "Illusion",
    "魔法师": "Spellcaster",
    "魔法師": "Spellcaster",
    "兽战士": "Beast-Warrior",
    "獸戰士": "Beast-Warrior",
    "爬虫类": "Reptile",
    "爬蟲類": "Reptile",
    "念动力": "Psychic",
    "念動力": "Psychic",
    "幻神兽": "Divine-Beast",
    "幻神獸": "Divine-Beast",
    "创造神": "Creator God",
    "創造神": "Creator God",
    "电子界": "Cyberse",
    "電子界": "Cyberse",
    "鸟兽": "Winged Beast",
    "鳥獸": "Winged Beast",
    "战士": "Warrior",
    "戰士": "Warrior",
    "天使": "Fairy",
    "恶魔": "Fiend",
    "惡魔": "Fiend",
    "不死": "Zombie",
    "机械": "Machine",
    "機械": "Machine",
    "岩石": "Rock",
    "植物": "Plant",
    "昆虫": "Insect",
    "昆蟲": "Insect",
    "恐龙": "Dinosaur",
    "恐龍": "Dinosaur",
    "海龙": "Sea Serpent",
    "海龍": "Sea Serpent",
    "幻龙": "Wyrm",
    "幻龍": "Wyrm",
    "水": "Aqua",
    "炎": "Pyro",
    "雷": "Thunder",
    "龙": "Dragon",
    "龍": "Dragon",
    "兽": "Beast",
    "獸": "Beast",
    "鱼": "Fish",
    "魚": "Fish",
    "通常": "Normal",
    "效果": "Effect",
    "融合": "Fusion",
    "仪式": "Ritual",
    "儀式": "Ritual",
    "灵魂": "Spirit",
    "靈魂": "Spirit",
    "同盟": "Union",
    "二重": "Gemini",
    "调整": "Tuner",
    "調整": "Tuner",
    "同调": "Synchro",
    "同步": "Synchro",
    "衍生物": "Token",
    "速攻": "Quick-Play",
    "永续": "Continuous",
    "永續": "Continuous",
    "装备": "Equip",
    "裝備": "Equip",
    "场地": "Field",
    "場地": "Field",
    "反击": "Counter",
    "反擊": "Counter",
    "反转": "Flip",
    "反轉": "Flip",
    "卡通": "Toon",
    "超量": "Xyz",
    "灵摆": "Pendulum",
    "靈擺": "Pendulum",
    "特殊召唤": "Special Summon",
    "特殊召喚": "Special Summon",
    "连接": "Link",
    "連接": "Link",
}


def log(message: str) -> None:
    print(f"[autopr-zh-tw] {message}", flush=True)


def fail(message: str) -> None:
    print(f"[autopr-zh-tw] ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        fail(f"Missing {label}: {path}")
    return path


def download_file(url: str, target: Path) -> None:
    log(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "TransSuperpre-AutoPR/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        with target.open("wb") as output:
            shutil.copyfileobj(response, output)
    log(f"Downloaded base package to {target}")


def fetch_json(url: str) -> list[dict]:
    log(f"Fetching {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "TransSuperpre-AutoPR/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        fail(f"Release JSON is not a list: {url}")
    return data

def resolve_cards_cdb(work_dir: Path) -> Path:
    env_path = os.environ.get("TW_AUTOPR_CARDS_CDB")
    if env_path:
        return require_file(Path(env_path).resolve(), "configured cards.cdb")

    cards_cdb = work_dir / "cards.cdb"
    download_file(CARDS_CDB_URL, cards_cdb)
    return cards_cdb


def extract_test_update_from_ypk(base_ypk: Path, target: Path) -> None:
    log("Extracting test-update.cdb from downloaded ypk")
    with zipfile.ZipFile(base_ypk, "r") as archive:
        try:
            with archive.open("test-update.cdb") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        except KeyError:
            fail(f"test-update.cdb was not found inside {base_ypk}")


def translate_test_update_cdb(target_path: Path, cards_cdb_path: Path) -> None:
    fields = ["name", "desc"] + [f"str{i}" for i in range(1, 17)]
    select_columns = ", ".join(fields)
    set_columns = ", ".join(f"{field}=?" for field in fields)

    log(f"Applying local cards.cdb translations from {cards_cdb_path}")
    src_conn = sqlite3.connect(str(cards_cdb_path))
    tgt_conn = sqlite3.connect(str(target_path))
    src_cur = src_conn.cursor()
    tgt_cur = tgt_conn.cursor()
    updated = 0
    missing = 0

    try:
        tgt_conn.execute("BEGIN")
        tgt_cur.execute("SELECT id FROM texts")
        ids = [row[0] for row in tgt_cur.fetchall()]

        for card_id in ids:
            src_cur.execute(f"SELECT {select_columns} FROM texts WHERE id=?", (card_id,))
            row = src_cur.fetchone()
            if row:
                tgt_cur.execute(f"UPDATE texts SET {set_columns} WHERE id=?", (*row, card_id))
                updated += 1
            else:
                missing += 1

        tgt_conn.commit()
        tgt_cur.execute("VACUUM")
        log(f"test-update.cdb translation complete: updated={updated}, missing_in_cards_cdb={missing}")
    finally:
        src_conn.close()
        tgt_conn.close()


def prepare_payloads(base_ypk: Path, work_dir: Path) -> dict[str, Path]:
    beta_cdb = require_file(CARDEDITOR_EXPANSIONS_DIR / "beta.cdb", "CardEditor expansions/beta.cdb")
    pre_strings = require_file(
        CARDEDITOR_EXPANSIONS_DIR / "pre-strings.conf",
        "CardEditor expansions/pre-strings.conf",
    )

    release_cdb = work_dir / "test-release.cdb"
    strings_conf = work_dir / "test-strings.conf"
    update_cdb = work_dir / "test-update.cdb"

    shutil.copy2(beta_cdb, release_cdb)
    shutil.copy2(pre_strings, strings_conf)
    log(f"Copied {beta_cdb} -> {release_cdb.name}")
    log(f"Copied {pre_strings} -> {strings_conf.name}")

    cards_cdb = resolve_cards_cdb(work_dir)
    extract_test_update_from_ypk(base_ypk, update_cdb)
    translate_test_update_cdb(update_cdb, cards_cdb)

    return {
        "test-release.cdb": release_cdb,
        "test-strings.conf": strings_conf,
        "test-update.cdb": update_cdb,
    }


def sync_base_files(payloads: dict[str, Path]) -> None:
    BASE_FILES_DIR.mkdir(parents=True, exist_ok=True)
    for name, source in sorted(payloads.items()):
        destination = BASE_FILES_DIR / name
        shutil.copy2(source, destination)
        log(f"Refreshed Base Files/{name}")


def replace_payloads_in_ypk(base_ypk: Path, output_ypk: Path, payloads: dict[str, Path]) -> None:
    temp_ypk = output_ypk.with_suffix(".tmp")
    names_to_replace = set(payloads)

    log("Replacing AutoPR payloads inside ypk")
    with zipfile.ZipFile(base_ypk, "r") as zin:
        with zipfile.ZipFile(temp_ypk, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in names_to_replace:
                    continue
                zout.writestr(item, zin.read(item.filename))

            for archive_name, source in sorted(payloads.items()):
                zout.write(source, arcname=archive_name)
                log(f"Added {source.name} as {archive_name}")

    temp_ypk.replace(output_ypk)

    with zipfile.ZipFile(output_ypk, "r") as check:
        missing = names_to_replace.difference(check.namelist())
    if missing:
        fail(f"Generated ypk is missing: {', '.join(sorted(missing))}")

    log(f"Wrote {output_ypk}")


def extract_id_from_pic_url(pic_url: str) -> str | None:
    match = re.search(r"/(\d+)\.(?:jpg|jpeg|png)(?:\?|$)", pic_url or "", flags=re.IGNORECASE)
    return match.group(1) if match else None


def translate_overall_string(value: object) -> object:
    if not isinstance(value, str):
        return value

    translated = value
    for source, target in REPLACEMENT_MAP.items():
        translated = translated.replace(source, target)
    return translated


def load_names(json_path: Path) -> set[str]:
    if not json_path.is_file():
        return set()

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log(f"Warning: could not read existing {json_path.name}: {exc}")
        return set()

    return {item.get("name") for item in data if isinstance(item, dict) and item.get("name")}


TYPE_MONSTER = 0x1
TYPE_SPELL = 0x2
TYPE_TRAP = 0x4
TYPE_NORMAL = 0x10
TYPE_EFFECT = 0x20
TYPE_FUSION = 0x40
TYPE_RITUAL = 0x80
TYPE_SPIRIT = 0x200
TYPE_UNION = 0x400
TYPE_GEMINI = 0x800
TYPE_TUNER = 0x1000
TYPE_SYNCHRO = 0x2000
TYPE_TOKEN = 0x4000
TYPE_QUICKPLAY = 0x10000
TYPE_CONTINUOUS = 0x20000
TYPE_EQUIP = 0x40000
TYPE_FIELD = 0x80000
TYPE_COUNTER = 0x100000
TYPE_FLIP = 0x200000
TYPE_TOON = 0x400000
TYPE_XYZ = 0x800000
TYPE_PENDULUM = 0x1000000
TYPE_SPSUMMON = 0x2000000
TYPE_LINK = 0x4000000

RACE_LABELS = {
    1: "Warrior", 2: "Spellcaster", 4: "Fairy", 8: "Fiend",
    16: "Zombie", 32: "Machine", 64: "Aqua", 128: "Pyro", 256: "Rock",
    512: "Winged Beast", 1024: "Plant", 2048: "Insect", 4096: "Thunder",
    8192: "Dragon", 16384: "Beast", 32768: "Beast-Warrior",
    65536: "Dinosaur", 131072: "Fish", 262144: "Sea Serpent",
    524288: "Reptile", 1048576: "Psychic", 2097152: "Divine-Beast",
    4194304: "Creator God", 8388608: "Wyrm", 16777216: "Cyberse",
    33554432: "Illusion",
}

ATTRIBUTE_LABELS = {
    1: "Earth", 2: "Water", 4: "Fire", 8: "Wind",
    16: "Light", 32: "Dark", 64: "Divine",
}

LINK_MARKERS = [
    (64, "↖"), (128, "↑"), (256, "↗"),
    (8, "←"), (32, "→"),
    (1, "↙"), (2, "↓"), (4, "↘"),
]


def stat_text(value: object) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "?"
    return "?" if number < 0 else str(number)


def cdb_level(raw_level: object) -> int:
    try:
        return int(raw_level) & 0xFF
    except (TypeError, ValueError):
        return 0


def pendulum_scales(raw_level: object) -> tuple[int, int]:
    try:
        level = int(raw_level)
    except (TypeError, ValueError):
        return 0, 0
    return (level >> 24) & 0xFF, (level >> 16) & 0xFF


def link_marker_text(marker_value: object) -> str:
    try:
        markers = int(marker_value)
    except (TypeError, ValueError):
        return ""
    return "".join(f"[{symbol}]" for bit, symbol in LINK_MARKERS if markers & bit)


def format_overall_string_from_datas(row: dict[str, object]) -> str:
    card_type = int(row.get("type") or 0)
    if card_type & TYPE_SPELL:
        tags = ["Spell"]
        for bit, label in (
            (TYPE_RITUAL, "Ritual"),
            (TYPE_QUICKPLAY, "Quick-Play"),
            (TYPE_CONTINUOUS, "Continuous"),
            (TYPE_EQUIP, "Equip"),
            (TYPE_FIELD, "Field"),
        ):
            if card_type & bit:
                tags.append(label)
        return f"[{'|'.join(tags)}]"

    if card_type & TYPE_TRAP:
        tags = ["Trap"]
        if card_type & TYPE_CONTINUOUS:
            tags.append("Continuous")
        if card_type & TYPE_COUNTER:
            tags.append("Counter")
        return f"[{'|'.join(tags)}]"

    tags = ["Monster"]
    if card_type & TYPE_NORMAL and not card_type & TYPE_EFFECT:
        tags.append("Normal")
    if card_type & TYPE_EFFECT:
        tags.append("Effect")
    for bit, label in (
        (TYPE_FUSION, "Fusion"),
        (TYPE_RITUAL, "Ritual"),
        (TYPE_SPIRIT, "Spirit"),
        (TYPE_UNION, "Union"),
        (TYPE_GEMINI, "Gemini"),
        (TYPE_TUNER, "Tuner"),
        (TYPE_SYNCHRO, "Synchro"),
        (TYPE_TOKEN, "Token"),
        (TYPE_FLIP, "Flip"),
        (TYPE_TOON, "Toon"),
        (TYPE_XYZ, "Xyz"),
        (TYPE_PENDULUM, "Pendulum"),
        (TYPE_SPSUMMON, "Special Summon"),
        (TYPE_LINK, "Link"),
    ):
        if card_type & bit:
            tags.append(label)

    race = RACE_LABELS.get(int(row.get("race") or 0), str(row.get("race") or ""))
    attribute = ATTRIBUTE_LABELS.get(int(row.get("attribute") or 0), str(row.get("attribute") or ""))
    header = f"[{'|'.join(tags)}] {race}/{attribute}"

    if card_type & TYPE_LINK:
        markers = link_marker_text(row.get("def"))
        suffix = f" {markers}" if markers else ""
        return f"{header}  [LINK-{cdb_level(row.get('level'))}] {stat_text(row.get('atk'))}/-{suffix}"

    star = "☆" if card_type & TYPE_XYZ else "★"
    out = f"{header}  [{star}{cdb_level(row.get('level'))}] {stat_text(row.get('atk'))}/{stat_text(row.get('def'))}"
    if card_type & TYPE_PENDULUM:
        left, right = pendulum_scales(row.get("level"))
        out += f"  {left}/{right}"
    return out


def pic_version_from_json(data: list[dict]) -> str:
    for item in data:
        if not isinstance(item, dict):
            continue
        match = re.search(r"[?&]version=([^&]+)", item.get("picUrl", ""))
        if match:
            return match.group(1)
    return "19.7"


def build_pic_url(card_id: int, version: str) -> str:
    return f"https://cdntx.moecube.com/ygopro-super-pre/data/pics/{card_id}.jpg?version={version}"


def write_release_json(cdb_path: Path, output_json: Path) -> list[dict]:
    data = fetch_json(JSON_URL)

    log(f"Reading translated texts from {cdb_path}")
    conn = sqlite3.connect(str(cdb_path))
    updated = 0
    missing = 0
    added = 0
    seen_ids: set[int] = set()
    pic_version = pic_version_from_json(data)

    try:
        rows = conn.execute(
            "SELECT d.id, d.type, d.atk, d.def, d.level, d.race, d.attribute, t.name, t.desc "
            "FROM datas d JOIN texts t ON t.id=d.id ORDER BY d.id"
        ).fetchall()
        rows_by_card_id = {
            int(row[0]): {
                "id": row[0], "type": row[1], "atk": row[2], "def": row[3], "level": row[4],
                "race": row[5], "attribute": row[6], "name": row[7], "desc": row[8],
            }
            for row in rows
        }

        for item in data:
            if not isinstance(item, dict):
                continue
            card_id_text = extract_id_from_pic_url(item.get("picUrl", ""))
            if card_id_text:
                card_id = int(card_id_text)
                seen_ids.add(card_id)
                row = rows_by_card_id.get(card_id)
                if row:
                    item["name"], item["desc"] = row["name"], row["desc"]
                    updated += 1
                else:
                    missing += 1
            item["overallString"] = translate_overall_string(item.get("overallString"))

        for card_id, row in rows_by_card_id.items():
            if card_id in seen_ids:
                continue
            data.append({
                "name": row["name"] or "",
                "desc": row["desc"] or "",
                "overallString": format_overall_string_from_datas(row),
                "picUrl": build_pic_url(card_id, pic_version),
            })
            added += 1
    finally:
        conn.close()

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    log(f"Wrote {output_json} (updated={updated}, missing_in_cdb={missing}, added={added})")
    return data


def write_version(output_dir: Path) -> None:
    version = str(int(time.time()))
    version_path = output_dir / "version.txt"
    version_path.write_text(version, encoding="utf-8", newline="\n")
    log(f"Wrote {version_path}: {version}")


def write_commit_body(new_cards: list[str]) -> None:
    body_path = OUTPUT_DIR / ".autopr-commit-body.txt"
    if new_cards:
        body = "新增卡片:\n" + "\n".join(f"- {name}" for name in new_cards) + "\n"
    else:
        body = "新增卡片:\n(無新卡)\n"
    body_path.write_text(body, encoding="utf-8", newline="\n")
    log(f"Wrote commit body helper {body_path}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    old_names = load_names(OUTPUT_DIR / "test-release.json")

    with tempfile.TemporaryDirectory(prefix=".autopr-work-", dir=OUTPUT_DIR) as temp_name:
        work_dir = Path(temp_name)
        base_ypk = work_dir / "ygopro-super-pre.download.tmp"
        download_file(YPK_URL, base_ypk)
        payloads = prepare_payloads(base_ypk, work_dir)
        sync_base_files(payloads)
        replace_payloads_in_ypk(base_ypk, OUTPUT_DIR / "ygopro-super-pre.ypk", payloads)
        new_data = write_release_json(payloads["test-release.cdb"], OUTPUT_DIR / "test-release.json")
        write_version(OUTPUT_DIR)

    new_names = {item.get("name") for item in new_data if isinstance(item, dict) and item.get("name")}
    write_commit_body(sorted(new_names - old_names))
    log("ZH-TW package build completed")


if __name__ == "__main__":
    main()