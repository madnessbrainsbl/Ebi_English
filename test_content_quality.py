import base64
import re
import sqlite3
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BASIC_DECKS = tuple(str(number) for number in range(1, 9))
FORBIDDEN_TRANSLATIONS = {
    "барахлить",
    "блевота",
    "блин",
    "возглавить",
    "вручать",
    "красться",
    "наоборот",
    "поливать",
    "просить",
    "старый",
}


class ContentQualityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(BASE_DIR / "content.db")

    def tearDown(self) -> None:
        self.connection.close()

    def test_goodbye_accepts_common_translations(self) -> None:
        translation = self.connection.execute(
            "SELECT ru FROM cards WHERE deck_id = ? AND en = ?", ("1", "Goodbye")
        ).fetchone()[0]
        self.assertEqual(
            set(translation.casefold().split("/")),
            {"пока", "прощай", "до свидания", "до встречи"},
        )

    def test_basic_decks_have_no_known_dictionary_noise(self) -> None:
        placeholders = ",".join("?" for _ in BASIC_DECKS)
        rows = self.connection.execute(
            f"SELECT ru FROM cards WHERE deck_id IN ({placeholders})", BASIC_DECKS
        )
        variants = {
            variant.strip().casefold()
            for (translation,) in rows
            for variant in translation.split("/")
        }
        self.assertFalse(variants & FORBIDDEN_TRANSLATIONS)

    def test_embedded_database_matches_content_database(self) -> None:
        source = (BASE_DIR / "content-db-b64.js").read_text(encoding="ascii")
        match = re.fullmatch(r'const CONTENT_DB_B64="([A-Za-z0-9+/=]+)";\n?', source)
        self.assertIsNotNone(match)
        self.assertEqual(
            base64.b64decode(match.group(1)),
            (BASE_DIR / "content.db").read_bytes(),
        )

    def test_imported_answers_do_not_contain_lesson_pages(self) -> None:
        contaminated = self.connection.execute(
            """
            SELECT count(*)
            FROM cards
            WHERE deck_id LIKE 'BEB1_%'
              AND (instr(ru, 'Правило') > 0 OR instr(ru, 'Полезная лексика:') > 0)
            """
        ).fetchone()[0]
        self.assertEqual(contaminated, 0)
        long_answers = self.connection.execute(
            "SELECT count(*) FROM cards WHERE length(ru) > 300"
        ).fetchone()[0]
        self.assertEqual(long_answers, 0)

    def test_grammar_prompts_start_in_english(self) -> None:
        prompts = self.connection.execute(
            """
            SELECT cards.en
            FROM cards
            JOIN decks ON decks.id = cards.deck_id
            WHERE decks.is_grammar = 1
            """
        )
        russian_prompts = []
        for (prompt,) in prompts:
            first_letter = re.search(r"[A-Za-zА-Яа-яЁё]", prompt)
            if first_letter and not first_letter.group().isascii():
                russian_prompts.append(prompt)
        self.assertEqual(russian_prompts, [])

    def test_science_series_have_source_backed_content(self) -> None:
        for series in ("SEC", "QUANT", "BIO"):
            decks, cards = self.connection.execute(
                """
                SELECT count(DISTINCT decks.id), count(cards.id)
                FROM decks
                JOIN cards ON cards.deck_id = decks.id
                WHERE decks.id LIKE ?
                """,
                (f"SCI_{series}_%",),
            ).fetchone()
            self.assertEqual(decks, 7)
            self.assertGreaterEqual(cards, 49)
        incomplete = self.connection.execute(
            """
            SELECT count(*)
            FROM cards
            WHERE deck_id LIKE 'SCI_%'
              AND (
                trim(example) = ''
                OR tip NOT LIKE 'Источник: %'
                OR (ru NOT GLOB '*[А-Яа-яЁё]*' AND lower(ru) <> lower(en))
              )
            """
        ).fetchone()[0]
        self.assertEqual(incomplete, 0)

    def test_science_sources_are_registered(self) -> None:
        sources = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM content_sources"
            )
        }
        self.assertTrue(
            {
                "MITRE ATT&CK",
                "OpenStax University Physics Volume 3",
                "OpenStax Biology 2e",
            }.issubset(sources)
        )

    def test_no_cards_have_empty_translations(self) -> None:
        empty = self.connection.execute(
            "SELECT count(*) FROM cards WHERE en IS NULL OR trim(en) = '' OR ru IS NULL OR trim(ru) = ''"
        ).fetchone()[0]
        self.assertEqual(empty, 0, f"Found {empty} cards with empty EN or RU translations")

    def test_no_duplicate_cards_per_deck(self) -> None:
        duplicates = self.connection.execute(
            """
            SELECT deck_id, lower(trim(en)), count(*)
            FROM cards
            GROUP BY deck_id, lower(trim(en))
            HAVING count(*) > 1
            """
        ).fetchall()
        self.assertEqual(duplicates, [], f"Found duplicate cards in decks: {duplicates[:5]}")

    def test_new_library_decks_present(self) -> None:
        expected_counts = {
            "LIB_IRREG_A2": 50,
            "LIB_IRREG_B1": 50,
            "LIB_PHRASAL_B1": 75,
            "LIB_PHRASAL_B2": 75,
        }
        for deck_id, count in expected_counts.items():
            actual = self.connection.execute(
                "SELECT count(*) FROM cards WHERE deck_id = ?", (deck_id,)
            ).fetchone()[0]
            self.assertEqual(actual, count, f"Unexpected card count for {deck_id}: {actual} != {count}")

        incomplete = self.connection.execute(
            """
            SELECT count(*) FROM cards
            WHERE deck_id IN ('LIB_IRREG_A2', 'LIB_IRREG_B1', 'LIB_PHRASAL_B1', 'LIB_PHRASAL_B2')
              AND (trim(example) = '' OR trim(tip) = '')
            """
        ).fetchone()[0]
        self.assertEqual(incomplete, 0, f"Found {incomplete} incomplete cards in new library decks")

        sources = {row[0] for row in self.connection.execute("SELECT name FROM content_sources")}
        self.assertTrue(
            {
                "English irregular verb forms",
                "WithEnglishWeCan Phrasal Verbs (Open Data)",
            }.issubset(sources)
        )

    def test_cefr_full_spectrum_decks_present(self) -> None:
        expected_counts = {
            "LIB_A0_PHONICS": 50,
            "LIB_A0_SURVIVAL": 30,
            "LIB_C1_ACADEMIC": 80,
            "LIB_C1_GRAMMAR": 40,
            "LIB_C1_COLLOCATIONS": 50,
            "LIB_C2_MASTERY": 80,
            "LIB_C2_NUANCES": 40,
            "LIB_C2_REGISTERS": 40,
        }
        for deck_id, count in expected_counts.items():
            actual = self.connection.execute(
                "SELECT count(*) FROM cards WHERE deck_id = ?", (deck_id,)
            ).fetchone()[0]
            self.assertEqual(actual, count, f"Unexpected card count for {deck_id}: {actual} != {count}")

        incomplete = self.connection.execute(
            """
            SELECT count(*) FROM cards
            WHERE deck_id IN (
                'LIB_A0_PHONICS', 'LIB_A0_SURVIVAL', 'LIB_C1_ACADEMIC', 'LIB_C1_GRAMMAR',
                'LIB_C1_COLLOCATIONS', 'LIB_C2_MASTERY', 'LIB_C2_NUANCES', 'LIB_C2_REGISTERS'
            ) AND (trim(example) = '' OR trim(tip) = '')
            """
        ).fetchone()[0]
        self.assertEqual(incomplete, 0, f"Found {incomplete} incomplete cards in full-spectrum CEFR decks")

        sources = {row[0] for row in self.connection.execute("SELECT name FROM content_sources")}
        self.assertTrue(
            {
                "English Phonics and Reading Rules Reference",
                "Averil Coxhead Academic Word List (AWL)",
                "Cambridge English C1-C2 Vocabulary and Grammar Guidelines",
            }.issubset(sources)
        )


if __name__ == "__main__":
    unittest.main()
