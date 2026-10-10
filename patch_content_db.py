from contextlib import closing
import base64
import json
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "content.db"
EMBEDDED_DATABASE_PATH = BASE_DIR / "content-db-b64.js"
FREEDICT_PATH = BASE_DIR / "freedict.js"

FALLBACK_WORDS: dict[str, str] = {
    "academia": "академия",
    "alphabetally": "по алфавиту",
    "am": "являюсь/есть",
    "analogue": "аналог",
    "analyse": "анализировать",
    "analyst": "аналитик",
    "analytic": "аналитический",
    "arena": "арена",
    "artifact": "артефакт",
    "be": "быть/находиться",
    "been": "был/была/были",
    "circulate": "циркулировать/распространять",
    "civilize": "цивилизовать",
    "cliche": "клише",
    "cluster": "кластер",
    "colonial": "колониальный",
    "copyright": "авторское право",
    "database": "база данных",
    "electrical": "электрический",
    "empirical": "эмпирический",
    "emulate": "эмулировать/подражать",
    "exam": "экзамен",
    "exemplar": "образец/экземпляр",
    "fact": "факт",
    "federate": "объединять в федерацию",
    "flora": "флора",
    "format": "формат",
    "gentleman": "джентльмен",
    "geological": "геологический",
    "globalisation": "глобализация",
    "has": "имеет/есть",
    "importation": "импорт/ввоз",
    "in": "в/внутри",
    "instrumental": "инструментальный",
    "interface": "интерфейс",
    "is": "есть/является",
    "member": "член/участник",
    "mythic": "мифический",
    "narcotic": "наркотический/наркотик",
    "nerves": "нервы",
    "nervous": "нервный",
    "online": "онлайн/в сети",
    "photo": "фото/фотография",
    "pint": "пинта",
    "playoff": "плей-офф",
    "portal": "портал",
    "portrait": "портрет",
    "privatise": "приватизировать",
    "prognosis": "прогноз",
    "pudding": "пудинг",
    "ranger": "рейнджер/лесничий",
    "reef": "риф",
    "regenerate": "регенерировать/восстанавливать",
    "regeneration": "регенерация/восстановление",
    "registration": "регистрация",
    "related": "связанный/родственный",
    "repertoire": "репертуар",
    "role": "роль",
    "ruins": "руины/развалины",
    "scenario": "сценарий",
    "sceptic": "скептик",
    "sceptical": "скептический",
    "sector": "сектор",
    "serial": "серийный/сериал",
    "serious": "серьёзный",
    "simulation": "симуляция/моделирование",
    "since": "с тех пор/поскольку",
    "soy": "соя/соевый",
    "speciality": "специальность/особенность",
    "specialize": "специализироваться",
    "sports": "спорт/спортивный",
    "statistics": "статистика",
    "suicidal": "суицидальный",
    "system": "система",
    "there": "там/туда",
    "tour": "тур/экскурсия/поездка",
    "transaction": "транзакция/сделка",
    "tribune": "трибуна",
    "tv": "телевидение/телевизор",
    "tyrant": "тиран",
    "was": "был/была/было",
    "were": "были",
    "would": "бы",
}


def load_freedict() -> dict[str, list[str]]:
    source = FREEDICT_PATH.read_text(encoding="utf-8")
    start = source.index("const FREEDICT = ") + len("const FREEDICT = ")
    payload = source[start:].rstrip().rstrip(";")
    return json.loads(payload)


def get_translation(word: str, freedict: dict[str, list[str]]) -> str:
    norm = word.lower().strip()
    if norm in FALLBACK_WORDS:
        return FALLBACK_WORDS[norm]
    if norm in freedict:
        return "/".join(freedict[norm][:3])
    clean = re.sub(r"[^a-z]", "", norm)
    if clean in FALLBACK_WORDS:
        return FALLBACK_WORDS[clean]
    if clean in freedict:
        return "/".join(freedict[clean][:3])
    raise ValueError(f"No translation found for: {word}")


def main() -> None:
    freedict = load_freedict()
    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        cur = connection.cursor()

        # 1. Fill missing translations
        cur.execute("SELECT id, en FROM cards WHERE ru IS NULL OR trim(ru) = ''")
        empty_cards = cur.fetchall()
        print(f"Found {len(empty_cards)} cards with empty translations to fix.")
        for card_id, en in empty_cards:
            translation = get_translation(en, freedict)
            cur.execute("UPDATE cards SET ru = ? WHERE id = ?", (translation, card_id))
        print(f"Updated {len(empty_cards)} cards.")

        # 2. Remove duplicate cards
        cur.execute("""
            DELETE FROM cards
            WHERE id NOT IN (
                SELECT min(id)
                FROM cards
                GROUP BY deck_id, lower(trim(en))
            )
        """)
        print(f"Removed {cur.rowcount} duplicate cards.")

        connection.commit()
        cur.execute("VACUUM")

    # 3. Re-encode to content-db-b64.js
    encoded = base64.b64encode(DATABASE_PATH.read_bytes()).decode("ascii")
    EMBEDDED_DATABASE_PATH.write_text(
        f'const CONTENT_DB_B64="{encoded}";\n', encoding="ascii"
    )
    print("Successfully updated content-db-b64.js")


if __name__ == "__main__":
    main()
