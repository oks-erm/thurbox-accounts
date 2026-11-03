"""Relay native SSO output and expose its intact authorization URL to the pane.

Only the short-lived browser URL is retained, in the account's private directory.
Native Claude still owns browser launch, stdin, login and credential storage.
"""
import codecs
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

from .core import atomic_write

HOSTS = {'claude.ai', 'console.anthropic.com', 'platform.claude.com'}


def valid_url(value):
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'https' and parsed.hostname in HOSTS and
                parsed.username is None and parsed.password is None and
                parsed.port in (None, 443) and parsed.path == '/oauth/authorize')
    except ValueError:
        return False


def link(profile):
    directory = Path(profile['directory'])
    lock_path = directory / 'login.lock'
    if not lock_path.is_file() or lock_path.is_symlink():
        return ''
    with lock_path.open() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            path = directory / 'login-link.json'
            if path.is_symlink():
                return ''
            try:
                data = json.loads(path.read_text())
                url = data.get('url', '')
                return url if data.get('expires_at', 0) > time.time() and valid_url(url) else ''
            except (OSError, ValueError, TypeError):
                return ''
    return ''


def login(executable, profile, env, output=None):
    output = output if output is not None else sys.stdout
    directory = Path(profile['directory'])
    path = directory / 'login-link.json'
    lock_path = directory / 'login.lock'
    if lock_path.is_symlink() or path.is_symlink():
        raise ValueError('Login state must not be a symlink')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('A login is already running for this account') from error
        path.unlink(missing_ok=True)
        try:
            # A pipe preserves the logical URL before the terminal soft-wraps it.
            # Stdin is inherited so native prompts/code entry keep working.
            with subprocess.Popen([executable, 'auth', 'login', '--sso'], env=env,
                                  cwd=directory, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT) as child:
                decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
                tail = ''
                try:
                    while chunk := child.stdout.read1(4096):
                        text = decoder.decode(chunk)
                        tail = (tail + text)[-32768:]
                        for match in re.finditer(r'https://[^\s\x1b]+(?=[\s\x1b])', tail):
                            url = match.group()
                            if valid_url(url):
                                atomic_write(path, json.dumps({'url': url, 'expires_at': time.time() + 900}))
                        output.write(text)
                        output.flush()
                    return child.wait()
                except BaseException:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                    raise
        finally:
            path.unlink(missing_ok=True)
