"""Keep console interrupts away from the browser's subprocesses."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


def supervise(command):
    with tempfile.TemporaryDirectory(prefix='profile-collector-stop-') as folder:
        stop_file = Path(folder) / 'stop'
        environment = os.environ.copy()
        environment['PROFILE_COLLECTOR_STOP_FILE'] = str(stop_file)
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        process = subprocess.Popen(command, env=environment, **options)
        notified = False

        def stop(signum=None, frame=None):
            nonlocal notified
            stop_file.touch()
            if not notified:
                print('Stop requested. Finishing the current browser operation and exporting saved profiles...', flush=True)
                notified = True

        previous = signal.signal(signal.SIGINT, stop)
        previous_break = signal.signal(signal.SIGBREAK, stop) if os.name == 'nt' else None
        try:
            while True:
                try:
                    return process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
                except KeyboardInterrupt:
                    stop()
        finally:
            signal.signal(signal.SIGINT, previous)
            if os.name == 'nt':
                signal.signal(signal.SIGBREAK, previous_break)
