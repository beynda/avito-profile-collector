from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.session import prepare_session
context = Mock()
logger = Mock()
context.new_page.return_value.is_closed.return_value = False
with patch('src.session.sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=''), patch('src.scraper.looks_like_captcha_or_block', return_value=False):
    assert prepare_session(context, logger)
with patch('src.session.sys.stdin.isatty', return_value=True), patch('builtins.input', return_value='q'):
    assert not prepare_session(context, logger)
with patch('src.session.sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=''), patch('src.scraper.looks_like_captcha_or_block', return_value=True):
    assert not prepare_session(context, logger)
context.reset_mock()
assert not prepare_session(context, logger, headless=True)
context.new_page.assert_not_called()
assert prepare_session(context, logger, headless=True, session_ready=True)
context.new_page.assert_not_called()
print('PASS: readiness, cancel, restriction, unattended confirmation')
