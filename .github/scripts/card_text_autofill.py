#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill prerelease card names/text from pack-numbered web sources."""

from __future__ import annotations

import html
import json
import re
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable


LogFn = Callable[[str], None]

YUGIPEDIA_API = "https://yugipedia.com/api.php"
OCG_LIST_URL = "https://ocg-card.com/list/{slug}/"
USER_AGENT = "TransSuperpre-CardTextAutofill/1.0"

EN_PEND_SEP = "----------------------------------------"
JP_PEND_SCALE_RE = re.compile(r"^\s*(\d+)\s*$")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")
TITLE_DISAMBIGUATOR_RE = re.compile(r"\s+\((?:card|anime|manga|video game|character|archetype|series)\)$", re.IGNORECASE)
YUGIPEDIA_LANG_FIELDS = {
    "en": ("", "text", "pendulum_effect"),
}
YUGIPEDIA_PEND_LABELS = {
    "en": ("Pendulum Scale", "Pendulum Effect", "Monster Effect"),
}

EXTRA_SET_CODES_BY_ID = {
    100200289: "VJMP-JP289",
    100200290: "VJMP-JP290",
    100260001: "YO12-JP001",
    100262001: "26TP-JP101",
    100264002: "VP26-JP002",
    100264003: "VP26-JP003",
}

OFFICIAL_SLUGS_BY_SET_PREFIX = {
    "26TP": "26tp",
    "VJMP": "vj7",
    "VP26": "vp26",
    "YO12": "yo",
}


@dataclass(frozen=True)
class PackEntry:
    card_id: int
    pack_code: str
    source_name: str


@dataclass(frozen=True)
class CardText:
    name: str
    desc: str
    source: str


def log_default(message: str) -> None:
    print(message, flush=True)


def request_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def load_pack_entries_from_ypk(ypk_path: Path) -> dict[int, PackEntry]:
    entries: dict[int, PackEntry] = {}
    if not ypk_path.is_file():
        return entries
    with zipfile.ZipFile(ypk_path, "r") as archive:
        names = [name for name in archive.namelist() if name.lower().startswith("pack/") and name.lower().endswith(".ydk")]
        for name in sorted(names):
            pack_code = pack_code_from_filename(Path(name).name)
            with archive.open(name) as handle:
                text = handle.read().decode("utf-8-sig", errors="replace")
            add_pack_entries(entries, pack_code, name, text)
    return entries


def load_pack_entries_from_dir(pack_dir: Path) -> dict[int, PackEntry]:
    entries: dict[int, PackEntry] = {}
    if not pack_dir.is_dir():
        return entries
    for path in sorted(pack_dir.glob("*.ydk")):
        add_pack_entries(entries, pack_code_from_filename(path.name), path.name, path.read_text(encoding="utf-8-sig", errors="replace"))
    return entries


def add_pack_entries(entries: dict[int, PackEntry], pack_code: str, source_name: str, text: str) -> None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.isdigit():
            continue
        card_id = int(line)
        entries[card_id] = PackEntry(card_id=card_id, pack_code=pack_code, source_name=source_name)


def pack_code_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if not stem:
        return ""
    return stem.split()[-1].upper()


def set_code_for_entry(entry: PackEntry, lang: str) -> str | None:
    if entry.pack_code.lower() == "etc":
        return EXTRA_SET_CODES_BY_ID.get(entry.card_id)
    base, sep, suffix = entry.pack_code.partition("-")
    if not base:
        return None
    number = entry.card_id % 1000
    if number <= 0:
        return None
    if lang == "en":
        prefix = entry.pack_code if sep else f"{base}-JP"
    elif lang == "jp":
        prefix = f"{base}-JP"
    else:
        return None
    return f"{prefix}{number:03d}"


def set_code_prefix(set_code: str) -> str:
    match = re.match(r"^([A-Z0-9]+)-", set_code or "")
    return match.group(1) if match else ""


def official_slug_for_set_code(set_code: str) -> str:
    prefix = set_code_prefix(set_code)
    return OFFICIAL_SLUGS_BY_SET_PREFIX.get(prefix, prefix.lower())


def pack_slug_for_entry(entry: PackEntry) -> str | None:
    set_code = set_code_for_entry(entry, "jp")
    if not set_code:
        return None
    return official_slug_for_set_code(set_code)


def normalize_lines(value: str) -> str:
    lines = [line.rstrip() for line in (value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def clean_wiki_text(value: str) -> str:
    text = value or ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{Ruby\|([^|{}]+)\|[^{}]*\}\}", r"\1", text)
    text = re.sub(r"\[\[File:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\{([^{}|]+)\|([^{}]+)\}\}", lambda match: match.group(2).split("|")[-1], text)
    text = re.sub(r"\{\{[^{}]+\}\}", "", text)
    text = html.unescape(text)
    return normalize_lines(text)


def clean_yugipedia_title(title: str) -> str:
    return TITLE_DISAMBIGUATOR_RE.sub("", title or "").strip()


def parse_card_table_params(wikitext: str) -> dict[str, str]:
    match = re.search(r"\{\{CardTable2\s*(?P<body>.*?)\n\}\}", wikitext or "", flags=re.DOTALL)
    if not match:
        return {}
    params: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in match.group("body").splitlines():
        if raw_line.startswith("|"):
            key, sep, value = raw_line[1:].partition("=")
            if not sep:
                current_key = None
                continue
            current_key = key.strip()
            params[current_key] = value.strip()
        elif current_key:
            params[current_key] += "\n" + raw_line.rstrip()
    return params


def format_yugipedia_card(title: str, params: dict[str, str], lang: str) -> CardText | None:
    name_key, text_key, pendulum_key = YUGIPEDIA_LANG_FIELDS[lang]
    name = clean_yugipedia_title(title) if lang == "en" else clean_wiki_text(params.get(name_key, ""))
    if not name:
        return None
    text = clean_wiki_text(params.get(text_key, ""))
    pendulum = clean_wiki_text(params.get(pendulum_key, ""))
    scale = clean_wiki_text(params.get("pendulum_scale", ""))
    if pendulum:
        scale_label, pendulum_label, monster_label = YUGIPEDIA_PEND_LABELS[lang]
        output = []
        if scale:
            output.append(f"{scale_label} = {scale}")
        output.append(f"[ {pendulum_label} ]")
        output.append(pendulum)
        output.append(EN_PEND_SEP)
        output.append(f"[ {monster_label} ]")
        if text:
            output.append(text)
        desc = normalize_lines("\n".join(output))
    else:
        desc = text
    if not desc:
        return None
    return CardText(name=name, desc=desc, source=f"Yugipedia:{title}")


def fetch_yugipedia_cards(set_codes: list[str], log: LogFn, lang: str = "en") -> dict[str, CardText]:
    cards: dict[str, CardText] = {}
    if lang not in YUGIPEDIA_LANG_FIELDS:
        return cards
    unique_codes = sorted({code for code in set_codes if code})
    for batch in chunked(unique_codes, 40):
        query = {
            "action": "query",
            "titles": "|".join(batch),
            "redirects": "1",
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "formatversion": "2",
        }
        url = YUGIPEDIA_API + "?" + urllib.parse.urlencode(query)
        try:
            data = json.loads(request_url(url))
        except Exception as exc:
            log(f"[SourceText] Yugipedia batch failed ({batch[0]}..): {exc}")
            continue

        redirects = {item.get("to"): item.get("from") for item in data.get("query", {}).get("redirects", [])}
        for page in data.get("query", {}).get("pages", []):
            if page.get("missing"):
                continue
            title = page.get("title", "")
            revisions = page.get("revisions") or []
            if not title or not revisions:
                continue
            params = parse_card_table_params(revisions[0].get("content", ""))
            card = format_yugipedia_card(title, params, lang)
            if not card:
                continue
            source_code = redirects.get(title)
            cards[source_code or title] = CardText(name=card.name, desc=card.desc, source=f"Yugipedia:{source_code or title}")
    return cards


class OcgCardListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: dict[str, CardText] = {}
        self.current_code: str | None = None
        self.current_name = ""
        self.pending_code: str | None = None
        self.in_td = False
        self.td_class = ""
        self.td_colspan = ""
        self.capture_text: list[str] = []
        self.skip_depth = 0
        self.pending_scale: str | None = None
        self.current_scale: str | None = None
        self.current_pendulum: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "td":
            self.in_td = True
            self.td_class = attrs_dict.get("class", "")
            self.td_colspan = attrs_dict.get("colspan", "")
            self.capture_text = []
            if "card-number" in self.td_class:
                self.pending_code = None
            elif self.is_name_class(self.td_class):
                self.current_name = ""
            elif "card-text" in self.td_class or "card-p-scale" in self.td_class:
                pass
        elif self.in_td and self.is_name_class(self.td_class) and tag == "div" and attrs_dict.get("class") == "card-ruby":
            self.skip_depth += 1
        elif self.skip_depth:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag != "td" or not self.in_td:
            return

        text = normalize_lines("".join(self.capture_text))
        if "card-number" in self.td_class:
            self.pending_code = text
            self.current_code = text
            self.current_name = ""
            self.current_pendulum = None
            self.pending_scale = None
            self.current_scale = None
        elif self.is_name_class(self.td_class):
            self.current_name = re.sub(r"(?:NEW|UP)\s*$", "", text).strip()
        elif "card-p-scale" in self.td_class:
            self.pending_scale = text
        elif "card-text" in self.td_class and self.current_code and self.current_name:
            if self.pending_scale or self.current_pendulum or self.td_colspan == "9":
                self.finish_text_cell(text)

        self.in_td = False
        self.td_class = ""
        self.td_colspan = ""
        self.capture_text = []

    def handle_data(self, data: str) -> None:
        if self.in_td and not self.skip_depth:
            self.capture_text.append(data)

    @staticmethod
    def is_name_class(class_name: str) -> bool:
        return any(token in class_name.split() for token in ("n-mon", "e-mon", "r-mon", "f-mon", "s-mon", "x-mon", "l-mon", "magic", "trap"))

    def finish_text_cell(self, text: str) -> None:
        if not text:
            return
        if self.pending_scale and JP_PEND_SCALE_RE.match(self.pending_scale):
            self.current_scale = self.pending_scale
            self.current_pendulum = text
            self.pending_scale = None
            return
        desc = text
        if self.current_pendulum:
            scale = self.current_scale or ""
            desc = "\n".join(
                [
                    f"【Ｐスケール：青{scale}／赤{scale}】" if scale else "【Ｐスケール】",
                    self.current_pendulum,
                    "【モンスター効果】",
                    text,
                ]
            )
            self.current_pendulum = None
            self.pending_scale = None
            self.current_scale = None
        self.cards[self.current_code] = CardText(name=self.current_name, desc=normalize_lines(desc), source=f"ocg-card:{self.current_code}")


def fetch_ocg_cards(slugs: list[str], log: LogFn) -> dict[str, CardText]:
    cards: dict[str, CardText] = {}
    for slug in sorted({item for item in slugs if item}):
        url = OCG_LIST_URL.format(slug=urllib.parse.quote(slug.lower()))
        try:
            page = request_url(url)
        except Exception as exc:
            log(f"[SourceText] OCG page failed ({slug}): {exc}")
            continue
        parser = OcgCardListParser()
        parser.feed(page)
        if parser.cards:
            cards.update(parser.cards)
            log(f"[SourceText] OCG {slug}: loaded={len(parser.cards)}")
        else:
            log(f"[SourceText] OCG {slug}: no card rows found")
    return cards


def current_cdb_names(cdb_path: Path) -> dict[int, str]:
    conn = sqlite3.connect(str(cdb_path))
    try:
        return {int(card_id): name or "" for card_id, name in conn.execute("SELECT id, name FROM texts")}
    finally:
        conn.close()


def fetch_yugipedia_by_existing_titles(names_by_id: dict[int, str], missing_ids: list[int], lang: str, log: LogFn) -> dict[int, CardText]:
    title_to_id = {
        name: card_id
        for card_id in missing_ids
        for name in [names_by_id.get(card_id, "").strip()]
        if name and not CJK_RE.search(name)
    }
    if not title_to_id:
        return {}
    cards = fetch_yugipedia_cards(sorted(title_to_id), log, lang=lang)
    output: dict[int, CardText] = {}
    for title, card_id in title_to_id.items():
        card = cards.get(title)
        if card:
            output[card_id] = card
    return output


def update_cdb_texts(cdb_path: Path, cards_by_id: dict[int, CardText], log: LogFn) -> int:
    if not cards_by_id:
        return 0
    conn = sqlite3.connect(str(cdb_path))
    changed = 0
    try:
        for card_id, card in cards_by_id.items():
            if not card.name or not card.desc:
                continue
            row = conn.execute("SELECT name, desc FROM texts WHERE id=?", (card_id,)).fetchone()
            if not row:
                continue
            if row[0] == card.name and row[1] == card.desc:
                continue
            conn.execute("UPDATE texts SET name=?, desc=? WHERE id=?", (card.name, card.desc, card_id))
            changed += 1
        conn.commit()
        if changed:
            conn.execute("VACUUM")
    finally:
        conn.close()
    log(f"[SourceText] Updated CDB rows={changed}")
    return changed


def build_id_to_set_code(entries: dict[int, PackEntry], ids: set[int], lang: str) -> dict[int, str]:
    id_to_code: dict[int, str] = {}
    for card_id in sorted(ids):
        entry = entries.get(card_id)
        if not entry:
            continue
        set_code = set_code_for_entry(entry, lang)
        if set_code:
            id_to_code[card_id] = set_code
    for card_id, set_code in EXTRA_SET_CODES_BY_ID.items():
        if card_id in ids:
            id_to_code.setdefault(card_id, set_code)
    return id_to_code


def autofill_cdb_from_pack_sources(cdb_path: Path, ypk_path: Path, lang: str, log_fn: LogFn | None = None) -> int:
    log = log_fn or log_default
    if lang not in {"en", "jp"}:
        return 0
    entries = load_pack_entries_from_ypk(ypk_path)
    if not entries:
        log(f"[SourceText] No pack/*.ydk entries found in {ypk_path}")
        return 0
    names_by_id = current_cdb_names(cdb_path)
    ids = set(names_by_id)
    id_to_code = build_id_to_set_code(entries, ids, lang)
    if not id_to_code:
        log("[SourceText] No set-code candidates matched the CDB")
        return 0

    cards_by_id: dict[int, CardText] = {}
    if lang in YUGIPEDIA_LANG_FIELDS:
        cards_by_code = fetch_yugipedia_cards(list(id_to_code.values()), log, lang=lang)
        for card_id, set_code in id_to_code.items():
            card = cards_by_code.get(set_code)
            if card:
                cards_by_id[card_id] = card
        missing_ids = [card_id for card_id in id_to_code if card_id not in cards_by_id]
        cards_by_id.update(fetch_yugipedia_by_existing_titles(names_by_id, missing_ids, lang, log))
    else:
        slugs = []
        for card_id in ids:
            entry = entries.get(card_id)
            if entry:
                slug = pack_slug_for_entry(entry)
                if slug:
                    slugs.append(slug)
        slugs.extend(official_slug_for_set_code(code) for code in id_to_code.values())
        cards_by_code = fetch_ocg_cards(slugs, log)
        for card_id, set_code in id_to_code.items():
            card = cards_by_code.get(set_code)
            if card:
                cards_by_id[card_id] = card

    missing = len(id_to_code) - len(cards_by_id)
    log(f"[SourceText] candidates={len(id_to_code)}, matched={len(cards_by_id)}, missing={missing}")
    return update_cdb_texts(cdb_path, cards_by_id, log)
