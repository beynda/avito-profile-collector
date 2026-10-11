from pathlib import Path
from unittest.mock import Mock, patch
import logging
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import scraper
page = Mock()
page.context._manual_verification_enabled = True
page.is_closed.return_value = False
logger = logging.getLogger('test')
with patch.object(scraper.sys.stdin, 'isatty', return_value=True), patch.object(scraper, 'looks_like_captcha_or_block', side_effect=[True, True, True, False]), patch('builtins.input', side_effect=['', '']) as prompt:
    assert scraper.wait_for_manual_verification(page, logger)
    assert prompt.call_count == 2
    page.close.assert_not_called()
with patch.object(scraper.sys.stdin, 'isatty', return_value=True), patch.object(scraper, 'looks_like_captcha_or_block', return_value=True), patch('builtins.input', return_value='q'):
    assert not scraper.wait_for_manual_verification(page, logger)
page.context._manual_verification_enabled = False
with patch.object(scraper, 'looks_like_captcha_or_block', return_value=True), patch('builtins.input') as prompt:
    assert not scraper.wait_for_manual_verification(page, logger)
    prompt.assert_not_called()
print('PASS: manual continue, repeated restriction, cancel, noninteractive mode')
