from contextlib import closing
import base64
import csv
import re
import sqlite3
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "content.db"
EMBEDDED_DATABASE_PATH = BASE_DIR / "content-db-b64.js"
CEFR_URL = "https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/master/cefrj-vocabulary-profile-1.5.csv"
TARGETS = {"A1": 250, "A2": 300, "B1": 350, "B2": 350}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def load_freedict() -> dict[str, list[str]]:
    source = (BASE_DIR / "freedict.js").read_text(encoding="utf-8")
    start = source.index("const FREEDICT = ") + len("const FREEDICT = ")
    payload = source[start:].rstrip().rstrip(";")
    import json

    return json.loads(payload)


def download_profile() -> list[dict[str, str]]:
    with urllib.request.urlopen(CEFR_URL, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def import_library() -> dict[str, int]:
    dictionary = load_freedict()
    profile = download_profile()
    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS content_sources (name TEXT PRIMARY KEY, url TEXT NOT NULL, license TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO content_sources (name,url,license) VALUES (?,?,?)",
            (
                "CEFR-J Vocabulary Profile 1.5",
                "https://github.com/openlanguageprofiles/olp-en-cefrj",
                "Commercial use permitted with citation; copyright Tono Laboratory, TUFS",
            ),
        )
        target_decks = tuple("LIB_CEFR_" + level for level in TARGETS)
        placeholders = ",".join("?" for _ in target_decks)
        existing = {
            normalize(row[0])
            for row in connection.execute(
                f"SELECT en FROM cards WHERE deck_id NOT IN ({placeholders})", target_decks
            )
            if normalize(row[0])
        }
        imported: dict[str, int] = {}
        for level, target in TARGETS.items():
            deck_id = "LIB_CEFR_" + level
            connection.execute("DELETE FROM cards WHERE deck_id = ?", (deck_id,))
            connection.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            connection.execute(
                "INSERT INTO decks (id,name,icon,is_grammar,cefr,ladder_pos) VALUES (?,?,?,?,?,?)",
                (
                    deck_id,
                    "CEFR-J · " + level + " · расширенный словарь",
                    "",
                    0,
                    level,
                    1000 + int(level[1:]),
                ),
            )
            selected: list[tuple[str, str]] = []
            seen: set[str] = set()
            for row in profile:
                word = row["headword"].strip().lower()
                word_key = normalize(word)
                translations = dictionary.get(word)
                if (
                    row["CEFR"] != level
                    or not re.fullmatch(r"[a-z]+(?:[-'][a-z]+)?", word)
                    or not translations
                    or word_key in existing
                    or word_key in seen
                ):
                    continue
                selected.append((word, "/".join(translations[:3])))
                seen.add(word_key)
                if len(selected) == target:
                    break
            if len(selected) < target:
                raise RuntimeError(f"Not enough translated {level} words: {len(selected)}")
            connection.executemany(
                "INSERT INTO cards (deck_id,en,ru,example,tip,sort_order) VALUES (?,?,?,?,?,?)",
                [
                    (deck_id, word, translation, "", "", index)
                    for index, (word, translation) in enumerate(selected)
                ],
            )
            imported[level] = len(selected)
    encoded = base64.b64encode(DATABASE_PATH.read_bytes()).decode("ascii")
    EMBEDDED_DATABASE_PATH.write_text(
        f'const CONTENT_DB_B64="{encoded}";\n', encoding="ascii"
    )
    return imported


if __name__ == "__main__":
    print(import_library())
