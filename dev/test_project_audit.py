"""Project regressions; all writes use temporary files or databases."""
import base64
import builtins
import contextlib
import csv
from contextlib import closing
import io
import json
import os
import shutil
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
import import_cefr_library as library
import import_cefr_full_spectrum as spectrum
import import_phrasal_and_irregular as phrasal


class ProjectAuditTest(unittest.TestCase):
    def test_context_grammar_matches_original_exercises(self):
        original = json.loads((ROOT / 'dev/context_grammar.json').read_text(encoding='utf-8'))
        self.assertEqual(len(original), 135)
        with closing(sqlite3.connect(f"file:{ROOT / 'content.db'}?mode=ro", uri=True)) as db:
            expected = {(c['deck_id'], c['en'], c['ru'], c['example'], c['tip']) for c in original}
            actual = set(db.execute("SELECT deck_id,en,ru,example,tip FROM cards WHERE deck_id IN ('CL_A2','CL_B1','CL_B2')"))
            self.assertEqual(actual, expected)

    def test_audio_references_have_attribution_and_license(self):
        with (ROOT / 'licenses/tatoeba-audio.tsv').open(encoding='utf-8', newline='') as source:
            credits = {row['audio_id']: row for row in csv.DictReader(source, delimiter='\t')}
        with closing(sqlite3.connect(f"file:{ROOT / 'content.db'}?mode=ro", uri=True)) as db:
            for (audio_id,) in db.execute('SELECT aid FROM audio_clips'):
                self.assertIn(str(audio_id), credits)
                self.assertTrue(credits[str(audio_id)]['author'])
                self.assertTrue(credits[str(audio_id)]['license'])

    def test_static_content_importers_are_repeatable(self):
        for module, entry in [(spectrum, 'import_full_spectrum'), (phrasal, 'import_all')]:
            with self.subTest(importer=module.__name__), tempfile.TemporaryDirectory() as folder:
                database = Path(folder) / 'content.db'
                embedded = Path(folder) / 'content-db-b64.js'
                shutil.copyfile(ROOT / 'content.db', database)
                with patch.multiple(module, DATABASE_PATH=database, EMBEDDED_DATABASE_PATH=embedded), contextlib.redirect_stdout(io.StringIO()):
                    getattr(module, entry)()
                    with closing(sqlite3.connect(database)) as db:
                        first = db.execute('SELECT deck_id,en,ru,example,tip,sort_order FROM cards ORDER BY deck_id,en').fetchall()
                    getattr(module, entry)()
                    with closing(sqlite3.connect(database)) as db:
                        second = db.execute('SELECT deck_id,en,ru,example,tip,sort_order FROM cards ORDER BY deck_id,en').fetchall()
                    self.assertEqual(first, second)
                    self.assertEqual(base64.b64decode(embedded.read_text().split('"')[1]), database.read_bytes())
    def test_shipped_database_integrity_and_card_ids(self):
        with closing(sqlite3.connect(f"file:{ROOT / 'content.db'}?mode=ro", uri=True)) as db, db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT count(*) FROM cards WHERE deck_id NOT IN (SELECT id FROM decks)").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM cards WHERE trim(en)='' OR en IS NULL OR trim(ru)='' OR ru IS NULL").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT deck_id,en FROM cards GROUP BY deck_id,en HAVING count(*)>1").fetchall(), [])
            self.assertEqual(db.execute("SELECT d.id FROM decks d LEFT JOIN cards c ON c.deck_id=d.id GROUP BY d.id HAVING count(c.id)=0").fetchall(), [])

    def test_pdf_modules_match_bundled_files(self):
        for embedded, module in [('pdf-lib-b64.js', 'pdf.min.mjs'), ('pdf-worker-b64.js', 'pdf.worker.min.mjs')]:
            source = (ROOT / embedded).read_text(encoding='ascii')
            self.assertEqual(base64.b64decode(source.split('"')[1]), (ROOT / module).read_bytes())

    def test_cefr_library_import_is_repeatable(self):
        dictionary = {'apple': ['яблоко'], 'banana': ['банан']}
        profile = [{'headword': word, 'CEFR': 'A1'} for word in dictionary]
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'content.db'
            embedded = Path(folder) / 'content-db-b64.js'
            with closing(sqlite3.connect(database)) as db, db:
                db.executescript('CREATE TABLE decks(id TEXT PRIMARY KEY,name TEXT,icon TEXT,is_grammar INTEGER,cefr TEXT,ladder_pos INTEGER); CREATE TABLE cards(id INTEGER PRIMARY KEY,deck_id TEXT,en TEXT,ru TEXT,example TEXT,tip TEXT,sort_order INTEGER);')
            with patch.multiple(library, DATABASE_PATH=database, EMBEDDED_DATABASE_PATH=embedded, TARGETS={'A1': 2}), patch.object(library, 'load_freedict', return_value=dictionary), patch.object(library, 'download_profile', return_value=profile):
                first = library.import_library()
                with closing(sqlite3.connect(database)) as db, db:
                    initial = db.execute('SELECT en,ru FROM cards ORDER BY en').fetchall()
                second = library.import_library()
                with closing(sqlite3.connect(database)) as db, db:
                    self.assertEqual(db.execute('SELECT en,ru FROM cards ORDER BY en').fetchall(), initial)
                self.assertEqual(first, second)

    def test_cli_eof_means_exit(self):
        with patch.object(builtins, 'input', side_effect=EOFError):
            self.assertEqual(main.ask('test'), 'q')

    def test_atomic_save_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = Path(folder) / 'progress.json'
            progress.write_text('{"original":true}', encoding='utf-8')
            with patch.object(main, 'PROGRESS_FILE', str(progress)), patch.object(os, 'replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    main.save_progress({'replacement': True})
            self.assertEqual(json.loads(progress.read_text()), {'original': True})
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_corrupt_cli_progress_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = Path(folder) / 'progress.json'
            progress.write_text('broken', encoding='utf-8')
            with patch.object(main, 'PROGRESS_FILE', str(progress)):
                with self.assertRaisesRegex(ValueError, 'Исходный файл сохранён'):
                    main.load_progress()
            self.assertEqual(progress.read_text(), 'broken')

    def test_cli_repeat_updates_card_and_session_counters(self):
        self.run_session_fixture(['wrong', 'яблоко'], expected=(1, 1, 2))

    def test_cli_quit_does_not_start_repeat_round(self):
        self.run_session_fixture(['wrong', 'q'], expected=(0, 1, 1), card_count=2)

    def run_session_fixture(self, answers, expected, card_count=1):
        card = {'en': 'apple', 'ru': 'яблоко', 'example': 'An apple.'}
        cards = [dict(card, en=f'apple{n}') for n in range(card_count)]
        vocab = {'levels': {'1': {'name': 'test', 'cards': cards}}}
        progress = {'cards': {}, 'unlocked_levels': ['1'], 'total_sessions': 0, 'total_correct': 0, 'total_wrong': 0}
        with patch.object(main, 'quiz_choice', side_effect=answers), patch.object(main, 'quiz_en_to_ru', side_effect=answers[1:]), patch.object(main.random, 'shuffle'), patch.object(main.time, 'sleep'), patch.object(main, 'clear'), patch.object(main, 'save_progress'), patch.object(main, 'log_mistake'), patch.object(main, 'log_session'), patch.object(main, 'check_unlock'), patch.object(main, 'show_session_results') as results, contextlib.redirect_stdout(io.StringIO()):
            main.run_session(progress, vocab)
        stats = results.call_args.args[0]
        self.assertEqual((stats['correct'], stats['wrong'], stats['reviewed']), expected)
        first = progress['cards']['1_apple0']
        self.assertEqual((first['correct'], first['wrong']), expected[:2])


if __name__ == '__main__':
    unittest.main()
