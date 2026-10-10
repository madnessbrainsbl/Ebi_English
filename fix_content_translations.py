from contextlib import closing
import base64
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "content.db"
EMBEDDED_DATABASE_PATH = BASE_DIR / "content-db-b64.js"

TRANSLATIONS: dict[tuple[str, str], str] = {
    ("1", "Hello/Hi"): "Привет/Здравствуй/Здравствуйте/Здорово",
    ("1", "Goodbye"): "Пока/Прощай/До свидания/До встречи",
    ("1", "Please"): "Пожалуйста",
    ("1", "Yes"): "Да/Ага",
    ("1", "Sorry"): "Прости/Извини/Извините",
    ("1", "Excuse me"): "Простите/Извините",
    ("2", "One"): "Один",
    ("2", "Two"): "Два",
    ("2", "Three"): "Три",
    ("2", "Five"): "Пять",
    ("2", "Ten"): "Десять",
    ("3", "Red"): "Красный/Рыжий",
    ("3", "Blue"): "Синий/Голубой",
    ("3", "Green"): "Зелёный",
    ("3", "Yellow"): "Жёлтый",
    ("3", "Black"): "Чёрный",
    ("3", "Orange"): "Оранжевый",
    ("3", "Pink"): "Розовый",
    ("3", "Brown"): "Коричневый/Бурый",
    ("4", "Mother/Mom/Mum"): "Мама/Мать",
    ("4", "Father/Dad"): "Папа/Отец",
    ("4", "Daughter"): "Дочь/Дочка",
    ("4", "Friend"): "Друг/Подруга/Приятель/Приятельница",
    ("4", "Wife"): "Жена/Супруга",
    ("4", "Husband"): "Муж/Супруг",
    ("4", "Baby"): "Малыш/Ребёнок/Младенец",
    ("5", "Water"): "Вода",
    ("5", "Milk"): "Молоко",
    ("5", "Coffee"): "Кофе",
    ("5", "Meat"): "Мясо",
    ("5", "Cheese"): "Сыр",
    ("5", "Sugar"): "Сахар",
    ("6", "Head"): "Голова",
    ("6", "Hand"): "Рука",
    ("6", "Eye"): "Глаз/Око",
    ("6", "Nose"): "Нос",
    ("6", "Mouth"): "Рот/Уста",
    ("6", "Ear"): "Ухо",
    ("6", "Back"): "Спина",
    ("6", "Sick"): "Больной/Нездоровый",
    ("8", "Door"): "Дверь",
    ("8", "Window"): "Окно/Окошко",
    ("8", "Bed"): "Кровать/Койка",
    ("8", "Floor"): "Пол/Этаж",
    ("P1", "A little"): "Немного/Чуть-чуть",
    ("BEB1_L1", "I'm at work now."): "Я сейчас на работе.",
    ("BEB1_L4", "What is there?"): "Что там?/Что там есть?",
    ("BEB1_L40", "He fought for his rights."): "Он боролся за свои права.",
}

GRAMMAR_CLOZES: dict[int, tuple[str, str]] = {
    7643: ("Write the number: 40", "forty"),
    7644: ("Write the number: 14", "fourteen"),
    7645: ("Write the number: 15", "fifteen"),
    7646: ("Write the number: 18", "eighteen"),
    7647: ("Write the number: 90", "ninety"),
    7667: ("The year 1990 is nineteen ___", "ninety"),
    7668: ("The year 2026 is twenty twenty-___", "six"),
    7672: ("Two times = ___", "twice"),
    7704: ("Reddish = redd___", "ish"),
    7705: ("Greenish = green___", "ish"),
    7706: ("The color of blood = blood-___", "colored"),
    7707: ("___ is my favorite color", "Blue"),
    7708: ("Dressed ___ black", "in"),
    7709: ("Go ___ with embarrassment", "red"),
    7710: ("Turn ___ with envy", "green"),
    7713: ("To ___ a picture (AmE)", "color"),
    7714: ("To ___ hair", "dye"),
    7715: ("To ___ the walls", "paint"),
    153: ("I ___ tired.", "am"),
    154: ("She ___ a doctor.", "is"),
    155: ("They ___ at home.", "are"),
    164: ("I ___ every day.", "work"),
    165: ("He ___ tea.", "drinks"),
    166: ("We ___ music.", "love"),
    167: ("She ___ the answer.", "knows"),
    177: ("___ cat is on the table.", "The"),
    185: ("I ___ a book.", "bought"),
    186: ("She ___ it.", "did"),
    187: ("We ___ home.", "went"),
    189: ("I ___ going to travel.", "am"),
    191: ("We ___ going to buy a house.", "are"),
    192: ("I ___ call you.", "will"),
    193: ("He ___ going to work.", "is"),
    195: ("Tomorrow ___ be sunny.", "will"),
    202: ("I ___ never been to London.", "have"),
    203: ("She ___ lost her keys.", "has"),
    211: ("I ___ go.", "must"),
    218: ("If it is warm, we ___ go.", "will"),
    219: ("If I knew, I ___ tell.", "would"),
    225: ("The book ___ written by him.", "was"),
    235: ("He is taller ___ me.", "than"),
    236: ("This is ___ cheapest option.", "the"),
    256: ("___ the house and the shop.", "Between"),
    257: ("___ the table.", "Under"),
}


def update_translations(connection: sqlite3.Connection) -> None:
    for (deck_id, english), russian in TRANSLATIONS.items():
        cursor = connection.execute(
            "UPDATE cards SET ru = ? WHERE deck_id = ? AND en = ?",
            (russian, deck_id, english),
        )
        if cursor.rowcount < 1:
            raise RuntimeError(f"Card not found: {deck_id}/{english}")
    connection.commit()


def trim_imported_lesson_text(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT id, en, ru
        FROM cards
        WHERE deck_id LIKE 'BEB1_%'
          AND (instr(ru, 'Правило') > 0 OR instr(ru, 'Полезная лексика:') > 0)
        """
    ).fetchall()
    for card_id, english, russian in rows:
        ending = english.rstrip()
        terminator = (
            "?" if ending.endswith("?") else "!" if ending.endswith("!") else "."
        )
        cutoffs: list[int] = []
        sentence_end = russian.find(terminator)
        if sentence_end >= 0:
            cutoffs.append(sentence_end + 1)
        page_break = re.search(r"\s+\d{1,3}\s+(?=[А-ЯЁA-Z])", russian)
        if page_break:
            cutoffs.append(page_break.start())
        for marker in (" Правило", " Полезная лексика:"):
            marker_at = russian.find(marker)
            if marker_at >= 0:
                cutoffs.append(marker_at)
        if not cutoffs:
            raise RuntimeError(f"Cannot isolate translation for card {card_id}")
        end = min(cutoffs)
        connection.execute(
            "UPDATE cards SET ru = ? WHERE id = ?", (russian[:end].strip(), card_id)
        )
    connection.commit()


def update_grammar_prompts(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT cards.id, cards.en, cards.ru, cards.example
        FROM cards
        JOIN decks ON decks.id = cards.deck_id
        WHERE decks.is_grammar = 1
        """
    ).fetchall()
    for card_id, prompt, answer, example in rows:
        example = example or ""
        first_letter = re.search(r"[A-Za-zА-Яа-яЁё]", prompt)
        if not first_letter or first_letter.group().isascii():
            continue
        if card_id in GRAMMAR_CLOZES:
            english_prompt, english_answer = GRAMMAR_CLOZES[card_id]
        else:
            english_prompt = ""
            for variant in sorted(answer.split("/"), key=len, reverse=True):
                candidate = re.sub(
                    re.escape(variant.strip()), "___", example, count=1, flags=re.I
                )
                if candidate != example and candidate.strip(" .") != "___":
                    english_prompt = candidate
                    break
            if not english_prompt:
                raise RuntimeError(f"Cannot build English grammar prompt for card {card_id}")
            english_answer = answer
        connection.execute(
            "UPDATE cards SET en = ?, ru = ? WHERE id = ?",
            (english_prompt, english_answer, card_id),
        )
    connection.commit()


def embed_database() -> None:
    encoded = base64.b64encode(DATABASE_PATH.read_bytes()).decode("ascii")
    EMBEDDED_DATABASE_PATH.write_text(
        f'const CONTENT_DB_B64="{encoded}";\n', encoding="ascii"
    )


def main() -> None:
    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        update_translations(connection)
        trim_imported_lesson_text(connection)
        update_grammar_prompts(connection)
    embed_database()


if __name__ == "__main__":
    main()
