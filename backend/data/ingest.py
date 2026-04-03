"""
Data ingestion script — loads curriculum into the items table.

Sources:
  Kana    : hardcoded (46 hiragana + 46 katakana)
  Vocab   : data/raw/vocab/jlpt_genki_combined_vocab.csv
  Kanji   : data/raw/kanji/jlpt_all_levels_kanji_code_friendly.csv
  Grammar : data/raw/grammar/JLPT Grammar.xlsx - full list.csv

Idempotent: uses deterministic UUID5 keyed on (type, japanese) so
re-runs never duplicate rows — ON CONFLICT (id) DO NOTHING is safe.

Run from backend/:
  python data/ingest.py
"""

import asyncio
import csv
import json
import os
import ssl
import uuid
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

RAW_DIR  = Path(__file__).parent / "raw"
_raw_url = os.getenv("DATABASE_URL", "")
DB_URL   = _raw_url.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")

# Stable namespace for deterministic UUIDs — never change this.
_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

BATCH_SIZE = 500


def stable_id(item_type: str, japanese: str) -> str:
    """Deterministic UUID5 based on (type, japanese). Same input → same UUID."""
    return str(uuid.uuid5(_NS, f"{item_type}:{japanese}"))


async def batch_insert(conn, rows: list[tuple]):
    """Insert a batch of item rows, skipping duplicates by id."""
    if not rows:
        return
    await conn.executemany("""
        INSERT INTO items (id, type, japanese, reading, meaning, jlpt_level, tags, examples, extra)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (id) DO NOTHING
    """, rows)


# ---------------------------------------------------------------------------
# Hiragana + Katakana (hardcoded)
# ---------------------------------------------------------------------------

HIRAGANA = [
    ("あ","a"),("い","i"),("う","u"),("え","e"),("お","o"),
    ("か","ka"),("き","ki"),("く","ku"),("け","ke"),("こ","ko"),
    ("さ","sa"),("し","shi"),("す","su"),("せ","se"),("そ","so"),
    ("た","ta"),("ち","chi"),("つ","tsu"),("て","te"),("と","to"),
    ("な","na"),("に","ni"),("ぬ","nu"),("ね","ne"),("の","no"),
    ("は","ha"),("ひ","hi"),("ふ","fu"),("へ","he"),("ほ","ho"),
    ("ま","ma"),("み","mi"),("む","mu"),("め","me"),("も","mo"),
    ("や","ya"),("ゆ","yu"),("よ","yo"),
    ("ら","ra"),("り","ri"),("る","ru"),("れ","re"),("ろ","ro"),
    ("わ","wa"),("を","wo"),("ん","n"),
]

KATAKANA = [
    ("ア","a"),("イ","i"),("ウ","u"),("エ","e"),("オ","o"),
    ("カ","ka"),("キ","ki"),("ク","ku"),("ケ","ke"),("コ","ko"),
    ("サ","sa"),("シ","shi"),("ス","su"),("セ","se"),("ソ","so"),
    ("タ","ta"),("チ","chi"),("ツ","tsu"),("テ","te"),("ト","to"),
    ("ナ","na"),("ニ","ni"),("ヌ","nu"),("ネ","ne"),("ノ","no"),
    ("ハ","ha"),("ヒ","hi"),("フ","fu"),("ヘ","he"),("ホ","ho"),
    ("マ","ma"),("ミ","mi"),("ム","mu"),("メ","me"),("モ","mo"),
    ("ヤ","ya"),("ユ","yu"),("ヨ","yo"),
    ("ラ","ra"),("リ","ri"),("ル","ru"),("レ","re"),("ロ","ro"),
    ("ワ","wa"),("ヲ","wo"),("ン","n"),
]


async def ingest_kana(conn):
    print("Ingesting hiragana + katakana...")
    rows = []
    for char, romaji in HIRAGANA:
        rows.append((
            stable_id("vocab", char), "vocab", char, romaji, romaji,
            "hiragana",
            json.dumps(["hiragana", "kana"]),
            json.dumps([]),
            json.dumps({}),
        ))
    for char, romaji in KATAKANA:
        rows.append((
            stable_id("vocab", char), "vocab", char, romaji, romaji,
            "katakana",
            json.dumps(["katakana", "kana"]),
            json.dumps([]),
            json.dumps({}),
        ))
    await batch_insert(conn, rows)
    print(f"  {len(HIRAGANA)} hiragana, {len(KATAKANA)} katakana")


# ---------------------------------------------------------------------------
# Vocab: jlpt_genki_combined_vocab.csv
#
# Columns: vocab_id, merge_key, kana, kanji, jlpt_level, jlpt_numeric,
#          english_definitions_json, sources_json, genki_chapters_json,
#          jmdict_seq_json, mapping_methods_json, matched_on_json
# ---------------------------------------------------------------------------

async def ingest_vocab(conn):
    csv_path = RAW_DIR / "vocab" / "jlpt_genki_combined_vocab.csv"
    if not csv_path.exists():
        print(f"  Skipping vocab — not found: {csv_path}")
        return

    print("Ingesting vocab...")
    rows = []
    skipped = 0

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kana  = (row.get("kana") or "").strip()
            kanji = (row.get("kanji") or "").strip()

            # Use kanji form as display when available, else fall back to kana
            japanese = kanji if kanji else kana
            reading  = kana if kanji else ""

            if not japanese:
                skipped += 1
                continue

            jlpt_level = (row.get("jlpt_level") or "").strip()
            if not jlpt_level:
                skipped += 1
                continue

            # Parse the first English definition from the JSON array
            try:
                definitions = json.loads(row.get("english_definitions_json") or "[]")
                meaning = definitions[0] if definitions else ""
            except (json.JSONDecodeError, IndexError):
                meaning = ""

            if not meaning:
                skipped += 1
                continue

            # Build tags
            tags = [jlpt_level.lower(), "vocab"]
            try:
                genki_chapters = json.loads(row.get("genki_chapters_json") or "[]")
                if genki_chapters:
                    tags.append("genki")
            except json.JSONDecodeError:
                genki_chapters = []

            try:
                sources = json.loads(row.get("sources_json") or "[]")
            except json.JSONDecodeError:
                sources = []

            extra = {"sources": sources, "genki_chapters": genki_chapters}

            rows.append((
                stable_id("vocab", japanese), "vocab", japanese, reading, meaning,
                jlpt_level,
                json.dumps(tags),
                json.dumps([]),
                json.dumps(extra),
            ))

            if len(rows) >= BATCH_SIZE:
                await batch_insert(conn, rows)
                rows = []

    await batch_insert(conn, rows)
    total = await conn.fetchval("SELECT COUNT(*) FROM items WHERE type = 'vocab'")
    print(f"  Done. vocab rows in DB: {total}  (skipped during parse: {skipped})")


# ---------------------------------------------------------------------------
# Kanji: jlpt_all_levels_kanji_code_friendly.csv
#
# Columns: row_id, jlpt_level, jlpt_numeric, index_within_level, kanji,
#          onyomi_raw, kunyomi_raw, meanings_raw,
#          onyomi_list_json, kunyomi_list_json, meanings_list_json,
#          vocab_count, vocab_json
# ---------------------------------------------------------------------------

async def ingest_kanji(conn):
    csv_path = RAW_DIR / "kanji" / "jlpt_all_levels_kanji_code_friendly.csv"
    if not csv_path.exists():
        print(f"  Skipping kanji — not found: {csv_path}")
        return

    print("Ingesting kanji...")
    rows = []
    skipped = 0

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            japanese = (row.get("kanji") or "").strip()
            if not japanese:
                skipped += 1
                continue

            jlpt_level = (row.get("jlpt_level") or "").strip()
            if not jlpt_level:
                skipped += 1
                continue

            onyomi_raw  = (row.get("onyomi_raw") or "").strip()
            kunyomi_raw = (row.get("kunyomi_raw") or "").strip()
            meanings_raw = (row.get("meanings_raw") or "").strip()

            if not meanings_raw:
                skipped += 1
                continue

            # reading = on-yomi; store both in extra
            reading = onyomi_raw

            try:
                onyomi_list  = json.loads(row.get("onyomi_list_json") or "[]")
            except json.JSONDecodeError:
                onyomi_list = []
            try:
                kunyomi_list = json.loads(row.get("kunyomi_list_json") or "[]")
            except json.JSONDecodeError:
                kunyomi_list = []

            # Use up to 3 vocab examples as item examples
            try:
                vocab_list = json.loads(row.get("vocab_json") or "[]")
                examples = [
                    {"sentence": v.get("expression", ""), "translation": v.get("meaning", "")}
                    for v in vocab_list[:3]
                ]
            except json.JSONDecodeError:
                examples = []

            extra = {
                "onyomi":   onyomi_list,
                "kunyomi":  kunyomi_list,
                "kunyomi_raw": kunyomi_raw,
            }

            tags = [jlpt_level.lower(), "kanji"]

            rows.append((
                stable_id("kanji", japanese), "kanji", japanese, reading, meanings_raw,
                jlpt_level,
                json.dumps(tags),
                json.dumps(examples),
                json.dumps(extra),
            ))

            if len(rows) >= BATCH_SIZE:
                await batch_insert(conn, rows)
                rows = []

    await batch_insert(conn, rows)
    total = await conn.fetchval("SELECT COUNT(*) FROM items WHERE type = 'kanji'")
    print(f"  Done. kanji rows in DB: {total}  (skipped during parse: {skipped})")


# ---------------------------------------------------------------------------
# Grammar: JLPT Grammar.xlsx - full list.csv
#
# No header row. Columns (11 total):
#   [0] jlpt_level  [1] index  [2] pattern  [3] romaji  [4] meaning
#   [5-9] empty     [10] source note
# ---------------------------------------------------------------------------

async def ingest_grammar(conn):
    csv_path = RAW_DIR / "grammar" / "JLPT Grammar.xlsx - full list.csv"
    if not csv_path.exists():
        print(f"  Skipping grammar — not found: {csv_path}")
        return

    print("Ingesting grammar...")
    rows = []
    skipped = 0

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for cols in reader:
            if len(cols) < 5:
                skipped += 1
                continue

            jlpt_level = cols[0].strip()
            japanese   = cols[2].strip()  # grammar pattern
            reading    = cols[3].strip()  # romaji
            meaning    = cols[4].strip()

            if not japanese or not meaning or not jlpt_level:
                skipped += 1
                continue

            tags = [jlpt_level.lower(), "grammar"]

            rows.append((
                stable_id("grammar", japanese), "grammar", japanese, reading, meaning,
                jlpt_level,
                json.dumps(tags),
                json.dumps([]),
                json.dumps({}),
            ))

            if len(rows) >= BATCH_SIZE:
                await batch_insert(conn, rows)
                rows = []

    await batch_insert(conn, rows)
    total = await conn.fetchval("SELECT COUNT(*) FROM items WHERE type = 'grammar'")
    print(f"  Done. grammar rows in DB: {total}  (skipped during parse: {skipped})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set in .env")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    print(f"Connecting to DB...")
    conn = await asyncpg.connect(DB_URL, ssl=ssl_ctx)

    try:
        await ingest_kana(conn)
        print()
        await ingest_vocab(conn)
        print()
        await ingest_kanji(conn)
        print()
        await ingest_grammar(conn)

        total = await conn.fetchval("SELECT COUNT(*) FROM items")
        by_type = await conn.fetch("SELECT type, COUNT(*) FROM items GROUP BY type ORDER BY type")
        print(f"\n{'-'*40}")
        print(f"Total items in DB: {total}")
        for record in by_type:
            print(f"  {record['type']:10s}  {record['count']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
