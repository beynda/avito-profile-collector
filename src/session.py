"""User-confirmed browser preparation before collection."""
import sys
from . import control

def prepare_session(context, logger, headless=False, session_ready=False):
    logger.info('This browser has its own local profile; it does not share your regular Chrome login.')
    if session_ready:
        logger.info('Browser preparation explicitly confirmed with --session-ready.')
        return True
    if headless or not sys.stdin.isatty():
        logger.error('First prepare the profile in a visible interactive browser. For a prepared unattended run, explicitly pass --session-ready.')
        return False
    page = context.new_page()
    page.goto('https://www.avito.ru', timeout=30000, wait_until='domcontentloaded')
    logger.info('Before collection: sign in manually if needed, complete any verification, and check that listings open normally in THIS browser.')
    logger.info('Login may help with session access, but is not guaranteed to remove restrictions. Passwords are never requested in this terminal.')
    try:
        control.waiting_for_input = True
        answer = control.prompt('When this browser is ready, press Enter to start collection. Type q to cancel: ')
    except EOFError:
        return False
    finally:
        control.waiting_for_input = False
    control.checkpoint()
    if answer.strip().lower() == 'q' or page.is_closed():
        return False
    from .scraper import looks_like_captcha_or_block
    if looks_like_captcha_or_block(page):
        logger.error('Access is still restricted. Collection will not start. Prepare the browser and try again later.')
        return False
    return True
