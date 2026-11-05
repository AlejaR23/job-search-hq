"""Offline checks for the CV trimmer and the CV length cap. Fictional text only."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c = load('cv_onepage')
SOURCE = '# EXAMPLE PERSON\nTagline | Example\nCity | x@example.com\n\n## Summary\nFirst sentence here. Second sentence here. Third sentence here.\n\n## Experience\n' + ''.join(
    f'**Role {r} | Company {r}** | 2020 to 2021\n' + ''.join(f'- Fictional bullet {r}.{b} ' + 'filler words ' * 14 + '\n' for b in range(1, 7)) for r in range(1, 7)) + '\n## Skills\nOne, two, three\n'


class Trim(unittest.TestCase):
    def run_trim(self, source=SOURCE):
        head, sections = c.trim(source)
        return c.render_md(head, sections), head, sections

    def test_result_fits_and_is_verbatim(self):
        text, head, sections = self.run_trim()
        self.assertLessEqual(c.height(head, sections), c.BUDGET)
        c.verify_subset(SOURCE, text)
        self.assertLess(len(text), len(SOURCE))

    def test_reworded_or_truncated_lines_are_refused(self):
        for bad in ('- Fictional bullet 1.1 filler', '- A brand new claim.', '## Summary\nFirst sentence'):
            with self.assertRaises(SystemExit):
                c.verify_subset(SOURCE, bad)

    def test_bullet_moved_under_another_role_is_refused(self):
        title = '**Role 2 | Company 2** | 2020 to 2021\n'
        moved = SOURCE.replace(title, title + '- Fictional bullet 1.1 ' + 'filler words ' * 14 + '\n', 1)
        with self.assertRaises(SystemExit):
            c.verify_subset(SOURCE, moved)

    def test_moved_sentences_are_refused(self):
        with self.assertRaises(SystemExit):
            c.verify_subset(SOURCE, '## Summary\nSecond sentence here. First sentence here.')


class WordCap(unittest.TestCase):
    def test_markdown_symbols_do_not_count(self):
        ai = load('ai_tasks')
        text = ' '.join(['- **word**'] * 550) + ' | | | ' * 100
        self.assertEqual(ai.word_count(text), 550)
        self.assertGreater(ai.word_count('word ' * 601), 600)


if __name__ == '__main__':
    unittest.main()
