"""Isolated Enterprise profiles and explicit, single-use conversation handoffs.

Credentials belong to the native Claude CLI. This module reads only its public
status output and the one conversation a user explicitly confirms transferring.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid

from .core import atomic_write, dumps
from .runtime import execute
from .thurbox import Thurbox, strict_json

SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,47}\Z')
STATUS_KEYS = {'loggedIn', 'authMethod', 'configDirectory', 'email', 'orgId', 'orgName', 'subscriptionType'}


def account_env(profile: dict, inherited: dict | None = None) -> dict:
    env = dict(os.environ if inherited is None else inherited)
    for key, value in env.items():
        if value and (key.startswith('ANTHROPIC_') or key.startswith('AWS_') or
                      key.startswith('GOOGLE_') or key.startswith('AZURE_') or
                      key in {'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_API_KEY_HELPER',
                              'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX',
                              'CLAUDE_CODE_USE_FOUNDRY', 'CLAUDE_CODE_CUSTOM_OAUTH_URL'}):
            raise ValueError(f'Conflicting environment variable {key}; use a clean Enterprise login environment')
    if env.get('CLAUDE_CONFIG_DIR') not in (None, '', profile['directory']):
        raise ValueError('Conflicting environment variable CLAUDE_CONFIG_DIR')
    env['CLAUDE_CONFIG_DIR'] = profile['directory']
    return env


def private_dir(path: Path):
    # Check every existing component before mkdir: no credential/history aliases.
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('Account paths must not contain symlinks')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('Account directory must be owned by this user with mode 0700')


class Profiles:
    def __init__(self, root: Path):
        self.root = root.expanduser().absolute()
        private_dir(self.root)

    @contextlib.contextmanager
    def lock(self, name='registry'):
        if not re.fullmatch(r'[a-zA-Z0-9-]+', name):
            raise ValueError('Invalid lock name')
        fd = os.open(self.root / (name + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError('Another account operation is in progress') from error
            yield
        finally:
            os.close(fd)

    def read(self, name, default=None):
        path = self.root / name
        if path.is_symlink():
            raise ValueError('Account state must not be a symlink')
        if not path.exists():
            return {} if default is None else default
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000 or info.st_mode & 0o077:
            raise ValueError('Account state must be a private regular file under 2 MB')
        return strict_json(path.read_text())

    def write(self, name, value):
        path = self.root / name
        if path.is_symlink():
            raise ValueError('Account state must not be a symlink')
        atomic_write(path, dumps(value) + '\n')

    def get(self, name):
        if not isinstance(name, str) or not SLUG.fullmatch(name):
            raise ValueError('Profile name must be a lowercase slug, up to 48 characters')
        value = self.read('profiles.json').get(name)
        if not value:
            raise ValueError('Unknown profile; use thurbox-accounts add NAME')
        path = self.root / 'profiles' / name
        private_dir(path)
        if value['directory'] != str(path):
            raise ValueError('Profile configuration path changed')
        return value

    def add(self, name, label=None):
        if not isinstance(name, str) or not SLUG.fullmatch(name):
            raise ValueError('Profile name must be a lowercase slug, up to 48 characters')
        label = label or name
        if not 1 <= len(label) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in label):
            raise ValueError('Label must be 1–80 printable characters')
        with self.lock():
            values = self.read('profiles.json')
            if name in values:
                raise ValueError('Profile already exists')
            path = self.root / 'profiles' / name
            if path.exists() or path.is_symlink():
                raise ValueError('Profile directory already exists; refusing to adopt it')
            private_dir(path)
            value = dict(name=name, label=label, directory=str(path))
            values[name] = value
            self.write('profiles.json', values)
            return value


class Claude:
    def __init__(self, executable='claude'):
        self.executable = executable

    def fingerprint(self):
        path = shutil.which(self.executable)
        if not path:
            raise ValueError('Claude CLI is not installed')
        path = Path(path).resolve()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def status(self, profile):
        result = execute([self.executable, 'auth', 'status', '--json'], Path(profile['directory']),
                         env=account_env(profile), timeout=20, limit=65536)
        if result['status'] not in {'PASS', 'FAIL'} or result['exit_code'] not in {0, 1} or result['truncated']:
            raise ValueError('Claude auth status failed; no credentials were imported')
        try:
            value = strict_json(result['stdout'])
            if not isinstance(value, dict) or type(value.get('loggedIn')) is not bool:
                raise ValueError()
            return {key: item for key, item in value.items() if key in STATUS_KEYS and
                    (isinstance(item, (str, bool)) or item is None)}
        except ValueError as error:
            raise ValueError('Claude returned an unsupported auth status schema') from error

    def login(self, profile):
        # Native interactive browser/SSO flow, no captured tokens or credential reads.
        return subprocess.call([self.executable, 'auth', 'login', '--sso'], env=account_env(profile),
                               cwd=profile['directory'])


class Accounts:
    def __init__(self, profiles: Profiles, claude: Claude, thurbox: Thurbox):
        self.profiles, self.claude, self.thurbox = profiles, claude, thurbox

    def status(self, name):
        profile = self.profiles.get(name)
        account_env(profile)
        result = self.claude.status(profile)
        if result.get('configDirectory') != profile['directory']:
            raise ValueError('Claude did not verify this profile directory; upgrade Claude CLI')
        if result.get('loggedIn') is not True:
            return result
        if result.get('authMethod') != 'claude.ai' or not result.get('email'):
            raise ValueError('Only native Claude Enterprise browser/SSO logins are supported')
        identity = {key: result[key] for key in ('email', 'orgId') if result.get(key)}
        with self.profiles.lock():
            values = self.profiles.read('profiles.json')
            pinned = values[name].get('identity')
            if pinned and pinned != identity:
                raise ValueError('Profile identity changed; create a separate profile for the other account')
            values[name]['identity'] = identity
            self.profiles.write('profiles.json', values)
        return result

    def authenticated(self, name):
        if self.status(name).get('loggedIn') is not True:
            raise ValueError('Profile is signed out; run thurbox-accounts login ' + name)
        return self.profiles.get(name)

    def check_launch(self, profile):
        plan = self.thurbox.call('agent', 'launch-args', 'claude')
        expected = shutil.which(self.claude.executable)
        command = shutil.which(plan.get('command', ''))
        if not expected or not command or Path(expected).resolve() != Path(command).resolve():
            raise ValueError('Thurbox Claude registry executable differs from --claude; align them before launching')
        account_env(profile, plan.get('env', {}))
        # The multiplexer server may predate this CLI and hold a different auth
        # environment. Inspect it privately and fail rather than clearing values.
        config = self.thurbox.call('version')
        socket = config.get('tmux_socket')
        if not isinstance(socket, str) or not socket:
            raise ValueError('Cannot verify the local Thurbox multiplexer environment')
        env = dict(os.environ)
        if config.get('tmux_tmpdir'):
            env['TMUX_TMPDIR'] = config['tmux_tmpdir']
        def tmux(*args):
            result = execute(['tmux', '-L', socket, *args], Path(profile['directory']),
                             env=env, timeout=10, limit=262144)
            if result['status'] == 'PASS' and not result['truncated']:
                return result['stdout']
            if result['status'] == 'FAIL' and not result['truncated'] and any(
                text in result.get('stderr', '') for text in ('no server running', 'No such file or directory')):
                return None
            raise ValueError('Cannot verify the local multiplexer environment')
        def parse(output, inherited):
            for line in (output or '').splitlines():
                if line.startswith('-'):
                    inherited.pop(line[1:], None)
                elif '=' in line:
                    key, value = line.split('=', 1)
                    inherited[key] = value
            return inherited
        global_env = parse(tmux('show-environment', '-g'), {})
        sessions = tmux('list-sessions', '-F', '#{session_id}')
        if sessions is None:
            account_env(profile, global_env)
        else:
            for identifier in sessions.splitlines():
                if not re.fullmatch(r'\$[0-9]+', identifier):
                    raise ValueError('Unexpected local multiplexer session topology')
                effective = tmux('show-environment', '-t', identifier)
                if effective is None:
                    raise ValueError('Multiplexer changed during account verification; retry')
                account_env(profile, parse(effective, dict(global_env)))

    def start(self, name, repo: Path, session_name: str, extra=None):
        profile = self.authenticated(name)
        self.check_launch(profile)
        repo = repo.expanduser().resolve(strict=True)
        if not repo.is_dir():
            raise ValueError('Repository must be an existing directory')
        with self.profiles.lock():
            bindings = self.profiles.read('bindings.json')
            value = self.thurbox.call('session', 'create', '--name', session_name, '--repo-path', str(repo),
                '--agent', 'claude', '--multiplexer', 'tmux', '--env', 'CLAUDE_CONFIG_DIR=' + profile['directory'],
                '--on-existing', 'fail', *(extra or []))
            if not isinstance(value.get('id'), str) or not value['id'] or value.get('created') is False:
                raise ValueError('Thurbox did not create a new session')
            bindings[value['id']] = dict(profile=name, identity=profile['identity'],
                cwd=str(repo), agent_session_id=value.get('agent_session_id'))
            try:
                self.profiles.write('bindings.json', bindings)
            except OSError as error:
                raise ValueError('Session created but binding failed: ' + value['id'] +
                                 '; stop it with thurbox-cli session stop before continuing') from error

        return value

    def compatible(self, name):
        profile = self.authenticated(name)
        proof = self.profiles.read('compatibility.json').get(name, {})
        if proof.get('fingerprint') != self.claude.fingerprint() or proof.get('identity') != profile['identity']:
            raise ValueError('Handoff disabled: run thurbox-accounts verify-handoff ' + name +
                             ' after login to prove native fork and restart support')
        return profile

    def source(self, ref):
        row = self.thurbox.call('session', 'get', ref)
        binding = self.profiles.read('bindings.json').get(row.get('id'))
        if not binding or row.get('agent') != 'claude' or row.get('host') or row.get('backend_type') not in {None, 'local:tmux', 'tmux'}:
            raise ValueError('Only local Claude sessions started by accounts start can be handed off')
        if row.get('stopped') is not True:
            raise ValueError('Use thurbox-cli session stop SOURCE at a safe point before previewing handoff')
        profile = self.profiles.get(binding['profile'])
        if profile.get('identity') != binding['identity'] or row.get('cwd') != binding['cwd']:
            raise ValueError('Source profile or working directory changed')
        identifier = str(uuid.UUID(row['agent_session_id']))
        if binding.get('agent_session_id') != identifier:
            raise ValueError('Source conversation identity changed')
        path = Path(row.get('transcript_path') or '')
        expected = Path(profile['directory']) / 'projects'
        if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(expected):
            raise ValueError('Source transcript must belong to the selected profile')
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError('Source transcript path contains a symlink')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 20_000_000 or path.name != identifier + '.jsonl':
            raise ValueError('Source transcript must be a regular conversation file under 20 MB')
        content = path.read_bytes()
        return row, binding, path, hashlib.sha256(content).hexdigest()

    def preview(self, ref, target):
        destination = self.compatible(target)
        self.check_launch(destination)
        row, binding, path, digest = self.source(ref)
        if binding['profile'] == target:
            raise ValueError('Source and target must be different profiles')
        plan = dict(id=uuid.uuid4().hex, expires=time.time() + 300, source=row['id'],
            source_profile=binding['profile'], source_identity=binding['identity'], target=target,
            target_identity=destination['identity'], cwd=row['cwd'], conversation=row['agent_session_id'],
            transcript=str(path), sha256=digest, state='preview',
            warning='This transfers the selected conversation context to the target organization.')
        with self.profiles.lock():
            plans = self.profiles.read('plans.json')
            # Expired previews carry no continuing authorization.
            plans = {key: value for key, value in plans.items() if value['expires'] > time.time()}
            plans[plan['id']] = plan
            self.profiles.write('plans.json', plans)
        return plan

    def confirm(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('Invalid confirmation ID')
        with self.profiles.lock():
            plans = self.profiles.read('plans.json')
            plan = plans.get(identifier)
            if not plan or plan['state'] != 'preview':
                raise ValueError('Unknown or already consumed confirmation')
            plan['state'] = 'consumed'
            self.profiles.write('plans.json', plans)
        with self.profiles.lock('session-' + plan['source']):
            if time.time() > plan['expires']:
                raise ValueError('Confirmation expired; preview again')
            target = self.compatible(plan['target'])
            self.check_launch(target)
            row, binding, path, digest = self.source(plan['source'])
            if (digest != plan['sha256'] or str(path) != plan['transcript'] or row['cwd'] != plan['cwd'] or
                row['agent_session_id'] != plan['conversation'] or binding['identity'] != plan['source_identity'] or
                target['identity'] != plan['target_identity']):
                raise ValueError('Conversation or account changed; preview again')
            folder = self.profiles.root / 'snapshots'
            private_dir(folder)
            snapshot = folder / (identifier + '.jsonl')
            # Read-only immutable-by-contract snapshot: never touch the original.
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('Conversation changed during confirmation')
            fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            operation = dict(source=row['id'], target=plan['target'], sha256=digest,
                state='forking', recovery=['thurbox-cli', 'session', 'start', row['id']])
            self.profiles.write('operation-' + identifier + '.json', operation)
            try:
                target_id = str(uuid.uuid4())
                operation['conversation'] = target_id
                self.profiles.write('operation-' + identifier + '.json', operation)
                self.native_fork(target, snapshot, target_id, Path(row['cwd']))
                operation.update(state='starting', conversation=target_id)
                self.profiles.write('operation-' + identifier + '.json', operation)
                result = self.start(plan['target'], Path(row['cwd']), 'handoff-' + identifier[:12],
                    ['--resume', target_id])
                if result.get('agent_session_id') != target_id:
                    raise ValueError('Destination conversation UUID was not retained; inspect the operation record')
                operation.update(state='created', destination=result['id'])
                return dict(**operation, note='Source remains stopped. Destination may need workspace trust confirmation.')
            except BaseException:
                operation['state'] = 'failed'
                raise
            finally:
                self.profiles.write('operation-' + identifier + '.json', operation)

    def native_fork(self, profile, snapshot, target_id, cwd):
        result = execute([self.claude.executable, '-p', '--tools', '', '--strict-mcp-config',
            '--resume', str(snapshot), '--fork-session', '--session-id', target_id,
            'Account handoff: do not perform prior tasks or use tools. Reply only HANDOFF-READY and await the user.'],
            cwd, env=account_env(profile), timeout=90, limit=65536)
        if result['status'] != 'PASS' or result['truncated']:
            raise ValueError('Native conversation fork failed; source remains stopped. See the operation recovery command.')
        matches = list((Path(profile['directory']) / 'projects').glob('*/' + target_id + '.jsonl'))
        if len(matches) != 1 or matches[0].is_symlink():
            raise ValueError('Destination transcript UUID could not be verified; source remains stopped')

    def verify_handoff(self, name):
        """Prove native pathname fork + explicit UUID + resume, using synthetic text only.

        This deliberately makes two tiny model requests under the selected account.
        A help flag alone is insufficient evidence that Thurbox restarts will work.
        """
        profile = self.authenticated(name)
        fingerprint = self.claude.fingerprint()
        folder = self.profiles.root / 'probes' / uuid.uuid4().hex
        private_dir(folder)
        source_id, target_id = str(uuid.uuid4()), str(uuid.uuid4())
        seed = folder / (source_id + '.jsonl')
        atomic_write(seed, json.dumps(dict(type='user', uuid=str(uuid.uuid4()), parentUuid=None,
            sessionId=source_id, cwd=str(folder), timestamp='2026-01-01T00:00:00.000Z',
            message=dict(role='user', content='Synthetic account-switch compatibility check. Remember marker NATIVE-FORK-OK.'))) + '\n')
        original = seed.read_bytes()
        common = [self.claude.executable, '-p', '--tools', '', '--strict-mcp-config',
                  '--setting-sources', '', '--max-budget-usd', '0.10']
        for extra in ([ '--resume', str(seed), '--fork-session', '--session-id', target_id,
                        'Reply with the marker from the previous message.'],
                      ['--resume', target_id, 'Reply with the same marker again.']):
            result = execute([*common, *extra], folder, env=account_env(profile), timeout=90, limit=65536)
            if result['status'] != 'PASS' or 'NATIVE-FORK-OK' not in result['stdout'] or result['truncated']:
                raise ValueError('Native fork/restart probe failed; handoff remains disabled. No real conversation was transferred.')
            matches = list((Path(profile['directory']) / 'projects').glob('*/' + target_id + '.jsonl'))
            if len(matches) != 1 or seed.read_bytes() != original:
                raise ValueError('Native fork did not preserve the source and destination UUID; handoff remains disabled')
        with self.profiles.lock():
            proofs = self.profiles.read('compatibility.json')
            proofs[name] = dict(fingerprint=fingerprint, identity=profile['identity'], verified=time.time())
            self.profiles.write('compatibility.json', proofs)
        return dict(profile=name, native_fork=True, native_restart=True)
