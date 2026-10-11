from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import unittest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_config, validate_config
import run

BASE = {'keywords': ['Example service'], 'regions': [{'slug': 'example/predlozheniya_uslug', 'name': 'Example city'}], 'database': {'path': 'data/state.db'}}

class ConfigTests(unittest.TestCase):
    def test_valid_defaults_and_relative_paths(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'config.yaml'
            path.write_text(yaml.safe_dump(BASE), encoding='utf-8')
            cfg = load_config(str(path))
            self.assertEqual(cfg.resolve(cfg.db_path), Path(folder) / 'data/state.db')
            self.assertFalse(cfg.browser.headless)

    def test_invalid_fields(self):
        cases = [None, [], {}, {**BASE, 'keywords': 'text'}, {**BASE, 'keywords': []},
                 {**BASE, 'regions': []}, {**BASE, 'regions': [{'slug': '../other', 'name': 'Example'}]},
                 {**BASE, 'regions': [{'slug': 'https://example.com', 'name': 'Example'}]},
                 {**BASE, 'database': {}}, {**BASE, 'database': {'path': ''}},
                 {**BASE, 'output': {'excel_path': 'data/state.db'}},
                 {**BASE, 'output': {'excel_path': 'same', 'csv_path': 'same'}},
                 {**BASE, 'max_pages_per_query': True}, {**BASE, 'max_pages_per_query': -1},
                 {**BASE, 'browser': {'headless': 'false'}}, {**BASE, 'browser': {'typo': 1}},
                 {**BASE, 'delays': {'between_pages_min': -1}},
                 {**BASE, 'delays': {'between_pages_min': float('nan')}},
                 {**BASE, 'delays': {'between_pages_min': 11, 'between_pages_max': 10}},
                 {**BASE, 'proxy': {'username': 'example'}}, {**BASE, 'unknown': 1}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_config(deepcopy(case))

    def test_cli_rejects_bad_yaml_before_browser(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'config.yaml'
            path.write_text('keywords: [', encoding='utf-8')
            with patch.object(run, 'launch_browser') as launch, self.assertRaises(SystemExit) as caught:
                run.main(['--collect', '--config', str(path)])
            self.assertEqual(caught.exception.code, 2)
            launch.assert_not_called()

    def test_conflicting_modes(self):
        with self.assertRaises(SystemExit) as caught:
            run.main(['--collect', '--export-only'])
        self.assertEqual(caught.exception.code, 2)

if __name__ == '__main__':
    unittest.main()
