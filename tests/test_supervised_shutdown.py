"""Verify graceful stop with a real isolated browser process."""
import os, sys, signal, subprocess, tempfile, time, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.supervisor import supervise
from src import control
from src.browser import launch_browser
from src.db import open_db, ProfileRecord
from src.export import export

if len(sys.argv) > 1:
    folder = Path(sys.argv[2])
    if sys.argv[1] == '--supervisor':
        sys.exit(supervise([sys.executable, __file__, '--worker', str(folder)]))
    driver, context = launch_browser(folder/'browser', True, None)
    try:
        with open_db(folder/'state.db') as db:
            db.upsert_profile(ProfileRecord('sample','https://example.com/profile','Sample','City','','','https://example.com/listing','Sample','sample'))
            page = context.new_page()
            page.set_content('<h1>Local shutdown fixture</h1>')
            (folder/'ready').touch()
            try:
                while True:
                    page.wait_for_timeout(200)
                    control.checkpoint()
            except KeyboardInterrupt:
                export(db, folder/'output.xlsx', folder/'output.csv', logging.getLogger('test'))
    finally:
        context.close()
        driver.stop()
    sys.exit(0)

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = subprocess.Popen([sys.executable,__file__,'--supervisor',directory], stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,**options)
    try:
        deadline = time.monotonic()+30
        while not (folder/'ready').exists():
            assert process.poll() is None, 'Worker stopped before browser was ready'
            assert time.monotonic()<deadline, 'Browser startup timed out'
            time.sleep(.1)
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
        output, errors = process.communicate(timeout=30)
        assert process.returncode == 0, errors
        assert (folder/'output.xlsx').is_file() and (folder/'output.csv').is_file()
        assert 'Traceback' not in errors and 'Event loop is closed' not in errors, errors
        print('PASS: real console stop, isolated browser shutdown, SQLite and both exports')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
