"""
Data ingestion script — loads JLPT vocab, kanji, and hiragana/katakana into the DB.

Data sources (all free/open):
  Vocabulary : https://github.com/scriptin/jlpt-vocab  (MIT)
  Kanji      : KANJIDIC2 from EDRDG  (CC Attribution)
  Grammar    : static JSON files in data/raw/grammar/

Run: python data/ingest.py
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

RAW_DIR   = Path(__file__).parent / "raw"
DB_URL    = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")  # asyncpg uses plain postgres:// URLs


# ---------------------------------------------------------------------------
# Hiragana + Katakana — hardcoded (46 characters each)
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


async def ingest_scripts(conn):
    print("Ingesting hiragana...")
    for char, romaji in HIRAGANA:
        await conn.execute("""
            INSERT INTO items (id, type, japanese, reading, meaning, jlpt_level, tags, examples, extra)
            VALUES ($1, 'vocab', $2, $3, $4, 'hiragana', $5, $6, $7)
            ON CONFLICT (id) DO NOTHING
        """,
            str(uuid.uuid4()), char, romaji, romaji,
            json.dumps(["hiragana", "kana"]),
            json.dumps([]),
            json.dumps({"row": _hiragana_row(char)}),
        )

    print("Ingesting katakana...")
    for char, romaji in KATAKANA:
        await conn.execute("""
            INSERT INTO items (id, type, japanese, reading, meaning, jlpt_level, tags, examples, extra)
            VALUES ($1, 'vocab', $2, $3, $4, 'katakana', $5, $6, $7)
            ON CONFLICT (id) DO NOTHING
        """,
            str(uuid.uuid4()), char, romaji, romaji,
            json.dumps(["katakana", "kana"]),
            json.dumps([]),
            json.dumps({}),
        )
    print(f"  Done: {len(HIRAGANA)} hiragana, {len(KATAKANA)} katakana")


def _hiragana_row(char: str) -> str:
    rows = {
        "あいうえお": "a-row",
        "かきくけこ": "k-row",
        "さしすせそ": "s-row",
        "たちつてと": "t-row",
        "なにぬねの": "n-row",
        "はひふへほ": "h-row",
        "まみむめも": "m-row",
        "やゆよ":     "y-row",
        "らりるれろ": "r-row",
        "わをん":     "w-row",
    }
    for group, row in rows.items():
        if char in group:
            return row
    return "unknown"


# ---------------------------------------------------------------------------
# JLPT Vocabulary — expects data/raw/vocab/N5.json, N4.json, etc.
# Each file: list of {word, reading, meaning, tags?}
# ---------------------------------------------------------------------------

async def ingest_vocab(conn):
    for level in ["N5", "N4", "N3"]:
        vocab_file = RAW_DIR / "vocab" / f"{level}.json"
        if not vocab_file.exists():
            print(f"  Skipping {level} vocab — file not found at {vocab_file}")
            continue

        with open(vocab_file) as f:
            items = json.load(f)

        count = 0
        for item in items:
            await conn.execute("""
                INSERT INTO items (id, type, japanese, reading, meaning, jlpt_level, tags, examples, extra)
                VALUES ($1, 'vocab', $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
            """,
                str(uuid.uuid4()),
                item["word"],
                item.get("reading", item["word"]),
                item["meaning"],
                level,
                json.dumps(item.get("tags", [])),
                json.dumps(item.get("examples", [])),
                json.dumps(item.get("extra", {})),
            )
            count += 1

        print(f"  {level} vocab: {count} items")


# ---------------------------------------------------------------------------
# Grammar — expects data/raw/grammar/N5.json, N4.json
# Each file: list of {pattern, meaning, structure?, examples?, tags?}
# ---------------------------------------------------------------------------

async def ingest_grammar(conn):
    for level in ["N5", "N4"]:
        grammar_file = RAW_DIR / "grammar" / f"{level}.json"
        if not grammar_file.exists():
            print(f"  Skipping {level} grammar — file not found at {grammar_file}")
            continue

        with open(grammar_file) as f:
            items = json.load(f)

        count = 0
        for item in items:
            await conn.execute("""
                INSERT INTO items (id, type, japanese, reading, meaning, jlpt_level, tags, examples, extra)
                VALUES ($1, 'grammar', $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
            """,
                str(uuid.uuid4()),
                item["pattern"],
                item.get("reading", item["pattern"]),
                item["meaning"],
                level,
                json.dumps(item.get("tags", ["grammar"])),
                json.dumps(item.get("examples", [])),
                json.dumps({"structure": item.get("structure", "")}),
            )
            count += 1

        print(f"  {level} grammar: {count} items")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print(f"Connecting to: {DB_URL[:40]}...")
    conn = await asyncpg.connect(DB_URL)
    try:
        await ingest_scripts(conn)
        print("\nIngesting vocabulary...")
        await ingest_vocab(conn)
        print("\nIngesting grammar...")
        await ingest_grammar(conn)
        print("\nIngestion complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
