"""Narrow desktop adapter; account/session policy stays in Accounts and Shared."""
import contextlib
from pathlib import Path
import shlex
import uuid

from .guard import writer_available
from .shared import Shared

KEYS = {'enter','escape','up','down','C-c'}
SHELLS = {'sh','bash','zsh','fish','dash','tcsh','login'}

class Desktop:
    def __init__(self, accounts):
        self.accounts = accounts
        self.store = accounts.profiles
        self.tb = accounts.thurbox
        self.shared = Shared(accounts)

    def records(self):
        result = {}
        for path in self.store.root.glob('shared-*.json'):
            if path.name == 'shared-proof.json':
                continue
            record = self.store.read(path.name)
            if not record.get('is_probe'):
                result[record.get('allowed_session') or 'pending:' + record['conversation']] = record
        return result

    def state(self):
        profiles = [dict(name=p['name'],label=p['label'],email=p.get('identity',{}).get('email','Login required'))
                    for name in self.store.read('profiles.json') for p in [self.store.get(name)]]
        bindings, records = self.store.read('bindings.json'), self.records()
        rows = self.tb.call('session','list').get('sessions',[])
        conversations = []
        originals = {record.get('original_session') for record in records.values()}
        for row in rows:
            owner = row.get('id')
            if row.get('host') or row.get('backend_type') not in {None,'tmux','local:tmux'} or owner in originals:
                continue
            record = records.get(owner)
            binding = bindings.get(owner)
            if record and row.get('agent') == 'claude-accounts':
                index = record['index']
                confirmed = record.get('mode',{}).get('active_index',index) if record['phase'] != 'active' else index
                conversations.append(dict(id=owner,name=row.get('name',owner),cwd=row['cwd'],
                    profile=record['profiles'][confirmed],next_profile=record['profiles'][(index+1)%len(record['profiles'])],
                    conversation=record['conversation'],shared=True,stopped=bool(row.get('stopped')),
                    phase=record['phase']))
            elif binding and row.get('agent') == 'claude':
                conversations.append(dict(id=owner,name=row.get('name',owner),cwd=row['cwd'],
                    profile=binding['profile'],shared=False,stopped=bool(row.get('stopped')),phase='stopped' if row.get('stopped') else 'running'))
        # Failed creates may leave only their durable reservation, not a row.
        present = {row['id'] for row in conversations}
        for owner, record in records.items():
            if owner and owner not in present and (record['phase'] in {'failed','switching'} or not record.get('allowed_session')):
                conversations.append(dict(id=owner,name='Resume failed conversation',cwd=record['cwd'],
                    profile=record['profiles'][record.get('mode',{}).get('active_index',record['index'])],shared=True,stopped=True,
                    phase=record['phase'] if record.get('allowed_session') else 'failed',conversation=record['conversation']))
        return dict(profiles=profiles,conversations=conversations)

    def owned(self, owner):
        records = self.records()
        record = records.get(owner)
        binding = self.store.read('bindings.json').get(owner)
        if not record and any(owner == value.get('original_session') or (binding and binding.get('agent_session_id') == value['conversation']) for value in records.values()):
            raise ValueError('This original conversation now uses shared history; select its current guarded session')
        if record and not record.get('allowed_session'):
            raise ValueError('Enrollment has no managed session yet; use Recover for this shared conversation')
        if not record and not binding:
            raise ValueError('Select a conversation owned by Accounts')
        row = self.tb.call('session','get',owner)
        if row.get('host') or row.get('backend_type') not in {None,'tmux','local:tmux'}:
            raise ValueError('Only owned local conversations are supported')
        if record:
            if row.get('agent') != 'claude-accounts' or row.get('agent_session_id') != record['conversation']:
                raise ValueError('Managed conversation identity changed')
            self.shared.validate(record)
        elif (row.get('agent') != 'claude' or row.get('agent_session_id') != binding.get('agent_session_id')
              or row.get('cwd') != binding.get('cwd')
              or self.store.get(binding['profile']).get('identity') != binding.get('identity')):
            raise ValueError('Owned conversation identity or agent changed')
        return row, record

    def capture(self, owner):
        pending = self.records().get(owner)
        if pending and not pending.get('allowed_session'):
            return dict(output='Shared enrollment needs recovery. History is preserved. Use Recover; missing/replaced references may require manual inspection.')
        row, _ = self.owned(owner)
        if row.get('stopped'):
            return dict(output='Conversation is stopped. Enable sharing or resume it before replying.')
        result = self.tb.call('session','capture',owner,'--lines','300')
        return dict(output=result.get('output',''))

    @contextlib.contextmanager
    def input_target(self, owner):
        row, record = self.owned(owner)
        lock = self.store.lock('transition-' + record['conversation']) if record else self.store.lock('transition-' + str(uuid.UUID(row['agent_session_id'])))
        with lock:
            row, record = self.owned(owner)
            if row.get('stopped'):
                raise ValueError('Conversation is stopped; no input was sent')
            if record:
                state = self.shared._runtime(record['conversation'])
                if (record['phase'] != 'active' or state.get('owner') != owner or state.get('phase') != 'running'
                        or not state.get('native_pid') or writer_available(self.store,record['conversation'])):
                    raise ValueError('Shared writer is not confirmed active; no input was sent')
            capture = self.tb.call('session','capture',owner,'--lines','1')
            foreground = Path(capture.get('foreground_process') or '').name
            command = shlex.split(capture.get('foreground_command') or '')
            expected = self.accounts.claude.executable
            known = foreground == 'claude' or expected in command or (record and any(Path(arg).name == 'thurbox-accounts-agent' for arg in command))
            if not foreground or foreground in SHELLS or not known:
                raise ValueError('Native Claude foreground cannot be confirmed; no input was sent')
            yield

    def send(self, owner, text):
        if not text.strip() or len(text.encode()) > 32_768 or '\x00' in text:
            raise ValueError('Reply must contain text and be at most 32 KB')
        with self.input_target(owner):
            try:
                return self.tb.call('session','send','--strict',owner,'--',text)
            except RuntimeError as error:
                if 'submission could not be confirmed' not in str(error):
                    raise
                # Thurbox confirms it typed the text, but cannot prove Enter
                # submitted it. Do not tell the user to send the prompt again.
                return dict(submitted=None,notice='Text was typed into Claude, but submission was not confirmed. Check the console; press Enter only if the native prompt still contains it.')

    def key(self, owner, key):
        if key not in KEYS:
            raise ValueError('Unsupported native prompt key')
        with self.input_target(owner):
            return self.tb.call('session','key',owner,key)

    def stop(self, owner):
        self.owned(owner)
        return self.tb.call('session','stop',owner)

    def start(self, owner):
        row, record = self.owned(owner)
        conversation = str(uuid.UUID(row['agent_session_id']))
        with self.store.lock('transition-' + conversation):
            row, record = self.owned(owner)
            if record:
                if record['phase'] != 'active':
                    raise ValueError('Shared conversation needs Recover, not an ordinary Resume')
                if not row.get('stopped'):
                    return dict(id=owner,already_running=True)
                return self.shared._launch(record,record['index'],recover=True)
            binding = self.store.read('bindings.json')[owner]
            profile = self.accounts.authenticated(binding['profile'])
            self.accounts.check_launch(profile)
            self.owned(owner)
            return self.tb.call('session','start',owner)
