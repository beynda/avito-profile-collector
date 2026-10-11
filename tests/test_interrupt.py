from pathlib import Path
import sys, tempfile, threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import control
from src.browser import launch_browser
control.requested = False
with tempfile.TemporaryDirectory() as folder:
    driver, context = launch_browser(Path(folder)/'profile', headless=True)
    try:
        page = context.new_page()
        timer = threading.Timer(0.05, control.request_stop, args=(None, None))
        timer.start()
        page.wait_for_timeout(200)
        timer.join()
        assert control.requested
        try:
            control.checkpoint()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('Stop was not observed')
    finally:
        context.close()
        driver.stop()
        control.requested = False
print('PASS: interruption deferred during real browser call; clean shutdown')
