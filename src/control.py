"""Defer console interruption until outside a browser API operation."""
import time
import os
from pathlib import Path

requested = False
waiting_for_input = False

def request_stop(signum, frame):
    global requested
    requested = True
    if waiting_for_input:
        raise KeyboardInterrupt

def checkpoint():
    path = os.environ.get('PROFILE_COLLECTOR_STOP_FILE')
    if requested or (path and Path(path).exists()):
        raise KeyboardInterrupt

def prompt(message):
    # A supervised Windows worker cannot receive Ctrl+C directly. Polling
    # keeps manual-verification prompts responsive to its stop request.
    if os.name != 'nt' or not os.environ.get('PROFILE_COLLECTOR_STOP_FILE'):
        return input(message)
    import msvcrt
    print(message, end='', flush=True)
    chars = []
    while True:
        checkpoint()
        if not msvcrt.kbhit():
            time.sleep(0.1)
            continue
        char = msvcrt.getwch()
        if char in ('\x00', '\xe0'):
            msvcrt.getwch()
        elif char in ('\r', '\n'):
            print()
            return ''.join(chars)
        elif char == '\x08':
            if chars:
                chars.pop()
                print('\b \b', end='', flush=True)
        elif char == '\x03':
            raise KeyboardInterrupt
        else:
            chars.append(char)
            print(char, end='', flush=True)

def sleep(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        checkpoint()
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    checkpoint()
