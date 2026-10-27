"""Selected shared history and serialized account transitions; no model requests."""
import os
from pathlib import Path
import time
import uuid

from .accounts import private_dir

AGENT = 'claude-accounts'
CONTRACT = 1


def identifier(value):
    return str(uuid.UUID(value))


def real_directory(path):
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError('Shared history parents must not be symlinks')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError('Shared history directory has an unexpected owner/type')


class Shared:
    def __init__(self, accounts):
        self.accounts = accounts
        self.store = accounts.profiles
        self.tb = accounts.thurbox

    def key(self, conversation):
        return 'shared-' + identifier(conversation) + '.json'

    def load(self, conversation):
        record = self.store.read(self.key(conversation))
        if not record:
            raise ValueError('Unknown shared conversation; enable sharing first')
        return record

    def save(self, record):
        self.store.write(self.key(record['conversation']), record)

    def proof_contract(self, names):
        if len(names) < 2 or len(set(names)) != len(names):
            raise ValueError('Select at least two distinct profiles in switching order')
        profiles = [self.accounts.authenticated(name) for name in names]
        return dict(contract=CONTRACT, fingerprint=self.accounts.claude.fingerprint(),
                    profiles=[dict(name=p['name'], identity=p['identity']) for p in profiles])

    def require_proof(self, names):
        contract = self.proof_contract(names)
        proofs = self.store.read('shared-proof.json')
        # One group is sufficient; changing membership/order/build requires new proof.
        if proofs != contract:
            raise ValueError('Shared switching disabled: run verify-shared for this ordered account group after login; native resume/compaction proof is required')
        return contract

    def validate(self, record):
        conversation = identifier(record['conversation'])
        expected = self.store.root / 'shared' / conversation
        for name, filename in [('transcript','main.jsonl'), ('sidecars','session')]:
            path = Path(record[name])
            if path != expected / filename or path.is_symlink():
                raise ValueError('Unexpected canonical history reference')
            if any(parent.is_symlink() for parent in path.parents):
                raise ValueError('Canonical history parent was replaced')
            if not path.exists() or path.stat().st_uid != os.getuid():
                raise ValueError('Canonical history is missing or has an unexpected owner')
        if not Path(record['transcript']).is_file() or not Path(record['sidecars']).is_dir():
            raise ValueError('Canonical history has an unexpected type')
        for alias in record['aliases']:
            profile = self.store.get(alias['profile'])
            base = Path(profile['directory']) / 'projects' / record['project']
            for key, suffix in [('transcript','.jsonl'),('sidecars','')]:
                path = Path(alias[key])
                if path != base / (conversation + suffix):
                    raise ValueError('Unrecognized shared history reference')
                for parent in path.parents:
                    if parent.is_symlink():
                        raise ValueError('Shared history reference parent was replaced')
                if not path.is_symlink() or path.resolve() != Path(record[key]):
                    raise ValueError('Shared history reference was replaced; preserved for manual recovery')

    def enroll(self, source, names, *, consent=False, launch=True):
        if not consent:
            raise ValueError('Explicit consent is required to share this conversation with the selected accounts')
        proof = self.require_proof(names)
        row, binding, path, digest = self.accounts.source(source)
        if binding['profile'] not in names:
            raise ValueError('Include the current account in the approved order')
        conversation = identifier(row['agent_session_id'])
        key = self.key(conversation)
        with self.store.lock('transition-' + conversation):
            if self.store.read(key):
                raise ValueError('Conversation already enrolled; use switch')
            profiles = [self.store.get(name) for name in names]
            for profile in profiles:
                self.accounts.check_launch(profile)
            folder = self.store.root / 'shared' / conversation
            private_dir(folder)
            aliases = []
            for profile in profiles:
                base = Path(profile['directory']) / 'projects' / path.parent.name
                real_directory(base)
                transcript = base / (conversation + '.jsonl')
                sidecars = base / conversation
                if transcript != path and (transcript.exists() or transcript.is_symlink()):
                    raise ValueError('Target already has this conversation UUID; no history was overwritten')
                if sidecars != path.with_suffix('') and (sidecars.exists() or sidecars.is_symlink()):
                    raise ValueError('Target already has this session folder; no history was overwritten')
                if sidecars.is_symlink() or (sidecars.exists() and not sidecars.is_dir()):
                    raise ValueError('Existing source sidecars must be a real directory')
                aliases.append(dict(profile=profile['name'], transcript=str(transcript), sidecars=str(sidecars)))
            canonical, sidecars = folder / 'main.jsonl', folder / 'session'
            if canonical.exists() or sidecars.exists():
                raise ValueError('A previous enrollment needs recovery; history was preserved')
            record = dict(conversation=conversation, project=path.parent.name, cwd=row['cwd'],
                transcript=str(canonical), sidecars=str(sidecars), aliases=aliases, profiles=names,
                proof=proof, index=names.index(binding['profile']), phase='enrolling',
                allowed_session='', reservation='', original_session=row['id'], original_sha256=digest)
            self.save(record)  # Persist recovery paths before the first move.
            try:
                os.rename(path, canonical)
                original_sidecars = path.with_suffix('')
                if original_sidecars.exists():
                    if not original_sidecars.is_dir():
                        raise ValueError('Source sidecars must be a directory')
                    os.rename(original_sidecars, sidecars)
                else:
                    sidecars.mkdir(mode=0o700)
                for alias in aliases:
                    Path(alias['transcript']).symlink_to(canonical)
                    Path(alias['sidecars']).symlink_to(sidecars, target_is_directory=True)
                record['phase'] = 'stopped'
                self.save(record)
                self.validate(record)
                return self._launch(record, record['index']) if launch else record
            except (OSError,ValueError,RuntimeError,TimeoutError) as error:
                record['phase'] = 'failed'
                self.save(record)
                raise ValueError(f'Shared enrollment failed; history preserved at {folder}. Inspect shared-status {conversation}: {error}') from error

    def _runtime(self, conversation):
        return self.store.read('runtime-' + conversation + '.json')

    def _launch(self, record, index, *, recover=False):
        from .guard import writer_available
        self.validate(record)
        if record.get('is_probe'):
            raise ValueError('Synthetic proof histories cannot be enrolled as managed conversations')
        self.require_proof(record['profiles'])
        target = self.accounts.authenticated(record['profiles'][index])
        self.accounts.check_launch(target)
        if not writer_available(self.store, record['conversation']):
            raise ValueError('A managed writer is still running; target was not launched')
        prior = self._runtime(record['conversation'])
        if prior.get('tools') or prior.get('subagents') or prior.get('blocked') or prior.get('uncertain'):
            raise ValueError('Previous worker activity or hook failure is unconfirmed; target was not launched')
        if prior.get('native_pid') or prior.get('phase') in {'starting','running'}:
            raise ValueError('Previous native process has not confirmed shutdown; inspect shared status')
        owner = record['allowed_session'] if recover else str(uuid.uuid4())
        record.update(index=index, phase='switching', allowed_session=owner,
                      reservation=record['reservation'] if recover else uuid.uuid4().hex)
        self.save(record)  # Durable reservation rejects old/competing managed starts.
        operation = dict(conversation=record['conversation'], destination=owner,
            target=target['name'], stage='launch', recovery=['thurbox-accounts','recover-shared',record['conversation']])
        self.store.write('switch-' + record['conversation'] + '.json', operation)
        try:
            existing = self.tb.call('session','list') if recover else {}
            rows = existing.get('sessions',[])
            if recover and any(row.get('id') == owner for row in rows):
                self.tb.call('session','start',owner)
            else:
                self.tb.call('session','create','--id',owner,'--name','shared-' + owner[:10],
                    '--repo-path',record['cwd'],'--agent',AGENT,'--multiplexer','tmux',
                    '--resume',record['conversation'],'--on-existing','fail',
                    '--env','CLAUDE_CONFIG_DIR=' + target['directory'],
                    '--env','THURBOX_ACCOUNTS_ROOT=' + str(self.store.root),
                    '--env','THURBOX_ACCOUNTS_CONVERSATION=' + record['conversation'],
                    '--env','THURBOX_ACCOUNTS_RESERVATION=' + record['reservation'],
                    '--env','THURBOX_ACCOUNTS_PROFILE=' + target['name'],
                    '--env','THURBOX_ACCOUNTS_CLAUDE=' + self.accounts.claude.executable)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                state = self._runtime(record['conversation'])
                if state.get('owner') == owner and state.get('phase') == 'running':
                    record['phase'] = 'active'
                    self.save(record)
                    operation['stage'] = 'active'
                    self.store.write('switch-' + record['conversation'] + '.json', operation)
                    result = dict(conversation=record['conversation'],session=owner,profile=target['name'],
                                  next_profile=record['profiles'][(index+1)%len(record['profiles'])])
                    try:
                        self.tb.call('session','focus',owner)
                    except (OSError,ValueError,RuntimeError,TimeoutError):
                        result['notice'] = 'Account resumed; select the new session in Thurbox manually'
                    return result
                if state.get('owner') == owner and state.get('error'):
                    raise ValueError(state['error'])
                time.sleep(0.1)
            raise TimeoutError('Target did not acquire its guarded writer lock; inspect shared status')
        except BaseException:
            record['phase'] = 'failed'
            self.save(record)
            raise

    def switch(self, conversation, *, expected_profile=None):
        conversation = identifier(conversation)
        with self.store.lock('transition-' + conversation):
            record = self.load(conversation)
            if record['phase'] != 'active':
                raise ValueError('Shared conversation needs recovery; use recover-shared ' + conversation)
            self.validate(record)
            self.require_proof(record['profiles'])
            next_index = (record['index']+1) % len(record['profiles'])
            if expected_profile and record['profiles'][next_index] != expected_profile:
                raise ValueError('Next account changed; refresh shared status before switching')
            target = self.accounts.authenticated(record['profiles'][next_index])
            self.accounts.check_launch(target)  # Validate before requesting source shutdown.
            owner = record['allowed_session']
            request = uuid.uuid4().hex
            self.store.write('control-' + conversation + '.json',dict(owner=owner,request=request,action='stop'))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = self._runtime(conversation)
                if state.get('owner') != owner:
                    raise ValueError('Managed source ownership changed')
                if state.get('request') == request and state.get('stop_result') == 'busy':
                    raise ValueError('Source is working, awaiting permission, or has no proven usage-limit stop; it remains running')
                if state.get('phase') == 'stopped' and not state.get('native_pid'):
                    if state.get('tools') or state.get('subagents') or state.get('blocked'):
                        raise ValueError('Stopped source still has unconfirmed tool/subagent activity; target was not launched')
                    break
                if state.get('error'):
                    raise ValueError(state['error'])
                time.sleep(0.1)
            else:
                raise TimeoutError('Source did not confirm safe shutdown; target was not launched')
            self.tb.call('session','stop',owner)
            if self.tb.call('session','get',owner).get('stopped') is not True:
                raise ValueError('Thurbox did not confirm source stopped')
            return self._launch(record,next_index)

    def recover(self, conversation):
        with self.store.lock('transition-' + identifier(conversation)):
            record = self.load(conversation)
            if record['phase'] not in {'failed','switching'} and (record['allowed_session'] or record['phase'] not in {'enrolling','stopped'}):
                raise ValueError('No failed managed session to recover; inspect shared status')
            if not record['allowed_session']:
                # Enrollment can finish its aliases then fail before reservation.
                # Missing/replaced references are preserved for manual repair.
                self.validate(record)
                return self._launch(record,record['index'])
            return self._launch(record,record['index'],recover=True)
