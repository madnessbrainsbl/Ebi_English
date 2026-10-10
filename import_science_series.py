from contextlib import closing
import base64
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "content.db"
EMBEDDED_DATABASE_PATH = BASE_DIR / "content-db-b64.js"
FREEDICT_PATH = BASE_DIR / "freedict.js"
ATTACK_URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"
PHYSICS_BASE_URL = "https://openstax.org/books/university-physics-volume-3/pages"
BIOLOGY_BASE_URL = "https://openstax.org/books/biology-2e/pages"
TRANSLATION_URL = "https://translate.googleapis.com/translate_a/single"
HEADERS = {"User-Agent": "GB-English-Cards/1.0"}
CARDS_PER_CHAPTER = 7

ATTACK_CHAPTERS = [
    ("Первоначальный доступ", "initial-access"),
    ("Выполнение", "execution"),
    ("Закрепление", "persistence"),
    ("Повышение привилегий", "privilege-escalation"),
    ("Скрытие активности", "stealth"),
    ("Доступ к учётным данным", "credential-access"),
    ("Воздействие", "impact"),
]

PHYSICS_CHAPTERS = [
    ("Относительность", 5),
    ("Фотоны и волны материи", 6),
    ("Квантовая механика", 7),
    ("Строение атома", 8),
    ("Физика конденсированного состояния", 9),
    ("Ядерная физика", 10),
    ("Частицы и космология", 11),
]

BIOLOGY_CHAPTERS = [
    ("Клеточная структура", 4),
    ("Деление клетки", 10),
    ("Генетика", 14),
    ("Биотехнологии", 17),
    ("Организация организма", 33),
    ("Эндокринная система", 37),
    ("Иммунная система", 42),
]


class DefinitionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.buffer = []
        self.terms = []

    def handle_starttag(self, tag, attrs):
        if tag in {"dt", "dd"}:
            self.active = tag
            self.buffer = []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == self.active:
            value = " ".join("".join(self.buffer).split())
            if tag == "dt":
                self.terms.append([value, ""])
            elif self.terms:
                self.terms[-1][1] = value
            self.active = None
            self.buffer = []


def fetch_bytes(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def clean_text(value, limit=260):
    value = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", value or "")
    value = re.sub(r"\(Citation:[^)]+\)", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[:limit].rsplit(" ", 1)[0] + "."
    return value


def read_freedict():
    raw = FREEDICT_PATH.read_text(encoding="utf-8")
    match = re.search(r"const FREEDICT = (\{.*\});\s*$", raw, re.S)
    return json.loads(match.group(1)) if match else {}


def existing_translations():
    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        return {
            english.casefold(): russian
            for english, russian in connection.execute(
                "SELECT en,ru FROM cards WHERE deck_id NOT LIKE 'SCI_%' AND ru IS NOT NULL AND trim(ru) <> ''"
            )
        }


def translate_term(term, known, dictionary):
    key = term.casefold()
    if key in known:
        return known[key]
    if key in dictionary and dictionary[key]:
        return dictionary[key][0]
    query = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "ru", "dt": "t", "q": term})
    try:
        data = json.loads(fetch_bytes(f"{TRANSLATION_URL}?{query}"))
        value = clean_text("".join(part[0] for part in data[0] if part and part[0]), 120)
        if value and value.casefold() != key:
            return value
    except Exception:
        pass
    translated = []
    for token in re.findall(r"[A-Za-z]+", key):
        values = dictionary.get(token)
        translated.append(values[0] if values else token)
    return " ".join(translated) or term


def translate_all(terms):
    known = existing_translations()
    dictionary = read_freedict()
    result = {}
    missing = sorted(set(terms), key=str.casefold)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(translate_term, term, known, dictionary): term
            for term in missing
        }
        for future in as_completed(futures):
            result[futures[future]] = future.result()
    return result


def attack_cards():
    payload = json.loads(fetch_bytes(ATTACK_URL))
    techniques = []
    for item in payload.get("objects", []):
        if item.get("type") != "attack-pattern" or item.get("revoked") or item.get("x_mitre_deprecated"):
            continue
        name = clean_text(item.get("name", ""), 90)
        if len(name) < 4:
            continue
        phases = {
            phase.get("phase_name")
            for phase in item.get("kill_chain_phases", [])
            if phase.get("kill_chain_name") == "mitre-attack"
        }
        external_id = ""
        for reference in item.get("external_references", []):
            if reference.get("source_name") == "mitre-attack":
                external_id = reference.get("external_id", "")
                break
        techniques.append({
            "name": name,
            "definition": clean_text(item.get("description", "")),
            "phases": phases,
            "source_id": external_id,
        })
    chapters = []
    used = set()
    for chapter_name, phase_name in ATTACK_CHAPTERS:
        candidates = sorted(
            (item for item in techniques if phase_name in item["phases"] and item["name"] not in used),
            key=lambda item: item["source_id"],
        )
        selected = candidates[:CARDS_PER_CHAPTER]
        used.update(item["name"] for item in selected)
        chapters.append((chapter_name, selected))
    return chapters


def openstax_cards(base_url, chapters):
    result = []
    for chapter_name, chapter_number in chapters:
        url = f"{base_url}/{chapter_number}-key-terms"
        parser = DefinitionParser()
        parser.feed(fetch_bytes(url).decode("utf-8", errors="replace"))
        selected = []
        seen = set()
        for term, definition in parser.terms:
            term = clean_text(term, 90)
            definition = clean_text(definition)
            key = term.casefold()
            if not term or not definition or key in seen or len(term) > 70:
                continue
            seen.add(key)
            selected.append({"name": term, "definition": definition, "source_id": f"Ch. {chapter_number}"})
            if len(selected) == CARDS_PER_CHAPTER:
                break
        if len(selected) < CARDS_PER_CHAPTER:
            raise RuntimeError(f"Недостаточно терминов в {url}")
        result.append((chapter_name, selected))
    return result


def load_series():
    return {
        "SEC": {
            "name": "Информационная безопасность",
            "cefr": "B1",
            "source": "MITRE ATT&CK",
            "url": "https://attack.mitre.org/",
            "chapters": attack_cards(),
        },
        "QUANT": {
            "name": "Квантовая механика и детерминизм",
            "cefr": "B2",
            "source": "OpenStax University Physics Volume 3",
            "url": "https://openstax.org/details/books/university-physics-volume-3",
            "chapters": openstax_cards(PHYSICS_BASE_URL, PHYSICS_CHAPTERS),
        },
        "BIO": {
            "name": "Клиническая биология",
            "cefr": "B2",
            "source": "OpenStax Biology 2e",
            "url": "https://openstax.org/details/books/biology-2e",
            "chapters": openstax_cards(BIOLOGY_BASE_URL, BIOLOGY_CHAPTERS),
        },
    }


def import_series():
    series_data = load_series()
    terms = [
        card["name"]
        for series in series_data.values()
        for _, cards in series["chapters"]
        for card in cards
    ]
    translations = translate_all(terms)
    result = {}
    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO content_sources (name,url,license) VALUES (?,?,?)",
            ("MITRE ATT&CK", "https://github.com/mitre-attack/attack-stix-data", "MITRE ATT&CK Terms of Use"),
        )
        connection.execute(
            "INSERT OR REPLACE INTO content_sources (name,url,license) VALUES (?,?,?)",
            ("OpenStax University Physics Volume 3", "https://openstax.org/details/books/university-physics-volume-3", "CC BY 4.0"),
        )
        connection.execute(
            "INSERT OR REPLACE INTO content_sources (name,url,license) VALUES (?,?,?)",
            ("OpenStax Biology 2e", "https://openstax.org/details/books/biology-2e", "CC BY 4.0"),
        )
        for series_id, series in series_data.items():
            connection.execute("DELETE FROM cards WHERE deck_id LIKE ?", (f"SCI_{series_id}_%",))
            connection.execute("DELETE FROM decks WHERE id LIKE ?", (f"SCI_{series_id}_%",))
            for chapter_index, (chapter_name, cards) in enumerate(series["chapters"], 1):
                deck_id = f"SCI_{series_id}_{chapter_index}"
                connection.execute(
                    "INSERT INTO decks (id,name,icon,is_grammar,cefr,ladder_pos) VALUES (?,?,?,?,?,?)",
                    (deck_id, f"{chapter_index}. {chapter_name}", "", 0, series["cefr"], 2000 + chapter_index),
                )
                connection.executemany(
                    "INSERT INTO cards (deck_id,en,ru,example,tip,sort_order) VALUES (?,?,?,?,?,?)",
                    [
                        (
                            deck_id,
                            card["name"],
                            translations[card["name"]],
                            card["definition"],
                            f"Источник: {series['source']} · {card['source_id']}",
                            index,
                        )
                        for index, card in enumerate(cards)
                    ],
                )
            result[series_id] = {
                "chapters": len(series["chapters"]),
                "cards": sum(len(cards) for _, cards in series["chapters"]),
                "source": series["source"],
            }
    encoded = base64.b64encode(DATABASE_PATH.read_bytes()).decode("ascii")
    EMBEDDED_DATABASE_PATH.write_text(f'const CONTENT_DB_B64="{encoded}";\n', encoding="ascii")
    return result


if __name__ == "__main__":
    print(json.dumps(import_series(), ensure_ascii=False, indent=2))
