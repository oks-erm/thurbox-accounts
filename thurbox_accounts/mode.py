"""Explicit, expiring adoption of one ordinary local conversation; no credentials."""
import hashlib
import os
from pathlib import Path
import stat
import shutil
import time
import uuid

from .accounts import account_env, private_dir
from .shared import Shared, identifier, real_directory

MAX_FILE = 20_000_000
MAX_TOTAL = 100_000_000
MAX_ENTRIES = 2000


def checked(path, *, directory=False):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Conversation history must have an absolute path')
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('Conversation history must not contain symlinks')
    info = path.stat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError('Conversation history has an unexpected owner, permissions or type')
    return info


def read_file(path):
    before = checked(path)
    if before.st_size > MAX_FILE:
        raise ValueError('Conversation history file exceeds 20 MB')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev,opened.st_ino) != (before.st_dev,before.st_ino):
            raise ValueError('Conversation history changed while opening')
        content = stream.read(MAX_FILE+1)
        after = os.fstat(stream.fileno())
    stamp = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if len(content) > MAX_FILE or stamp(opened) != stamp(after):
        raise ValueError('Conversation history changed while reading')
    return content, dict(size=after.st_size,device=after.st_dev,inode=after.st_ino,
                        mtime=after.st_mtime_ns,sha256=hashlib.sha256(content).hexdigest())


def manifest(path, *, sidecars=None):
    _, main = read_file(path)
    result = {'main':main}; total = main['size']
    sidecars = sidecars if sidecars is not None else path.with_suffix('')
    if sidecars.exists() or sidecars.is_symlink():
        checked(sidecars,directory=True)
        pending = [sidecars]
        while pending:
            folder = pending.pop(); checked(folder,directory=True)
            for child in sorted(folder.iterdir()):
                if len(result) >= MAX_ENTRIES:
                    raise ValueError('Conversation sidecars exceed 2000 entries')
                key = 'session/' + str(child.relative_to(sidecars))
                if child.is_symlink():
                    raise ValueError('Conversation sidecars must not contain symlinks')
                if child.is_dir():
                    checked(child,directory=True); result[key]={'directory':True}; pending.append(child)
                else:
                    _, item = read_file(child); total += item['size']; result[key]=item
                if total > MAX_TOTAL:
                    raise ValueError('Conversation history and sidecars exceed 100 MB')
    return result


class Mode:
    def __init__(self, accounts):
        self.accounts = accounts
        self.store = accounts.profiles
        self.tb = accounts.thurbox
        self.shared = Shared(accounts)

    def source(self, session, names):
        row = self.tb.call('session','get',session)
        if row.get('host') or row.get('backend_type') not in {None,'tmux','local:tmux'} or row.get('agent') != 'claude':
            raise ValueError('Switching mode supports ordinary local Claude conversations in WSL/macOS/Linux only')
        if row.get('stopped') is not True:
            raise ValueError('Finish tools and shell jobs, then stop this conversation in Thurbox before enabling switching')
        if row.get('background_work') or row.get('active_tools') or row.get('subagents') or row.get('blocked'):
            raise ValueError('Source still has unconfirmed background work or permissions; finish it before setup')
        native = identifier(row['agent_session_id'])
        launch = self.tb.call('agent','launch-args','claude','--session',row['id'])
        expected = shutil.which(self.accounts.claude.executable)
        executable = shutil.which(launch.get('command',''))
        if not expected or not executable or Path(expected).resolve() != Path(executable).resolve():
            raise ValueError('Source Claude executable differs from the verified native build')
        directory = Path(launch.get('env',{}).get('CLAUDE_CONFIG_DIR') or Path.home()/'.claude')
        checked(directory,directory=True)
        account_env(dict(directory=str(directory)),launch.get('env',{}))
        source = self.accounts.claude.status(dict(name='source',directory=str(directory)))
        if (source.get('loggedIn') is not True or source.get('authMethod') != 'claude.ai'
                or source.get('configDirectory') != str(directory) or not source.get('email')):
            raise ValueError('Cannot verify the source native browser/SSO account and directory')
        identity = {key:source[key] for key in ('email','orgId') if source.get(key)}
        profiles = [self.accounts.authenticated(name) for name in names]
        matches = [p for p in profiles if p['identity'] == identity]
        if len(matches) != 1:
            raise ValueError('Include exactly one matching source account in the selected accounts; source identity could not be matched')
        for profile in profiles: self.accounts.check_launch(profile)
        path = Path(row.get('transcript_path') or '')
        checked(path)
        if (path.name != native+'.jsonl' or path.parent.parent != directory/'projects'
                or path != path.resolve()):
            raise ValueError('Source transcript does not belong to the verified native account directory')
        checked(path.parent,directory=True)
        value = dict(session=row['id'],conversation=native,cwd=row['cwd'],name=row.get('name',row['id']),
                    source_profile=matches[0]['name'],source_identity=identity,directory=str(directory),
                    transcript=str(path),manifest=manifest(path))
        self._row_unchanged(value)
        return value

    def _row_unchanged(self, plan):
        row = self.tb.call('session','get',plan['session'])
        expected = dict(id=plan['session'],agent='claude',agent_session_id=plan['conversation'],
                        cwd=plan['cwd'],transcript_path=plan['transcript'],stopped=True)
        if (any(row.get(k) != v for k,v in expected.items()) or row.get('host')
                or row.get('backend_type') not in {None,'tmux','local:tmux'}
                or row.get('background_work') or row.get('active_tools') or row.get('subagents') or row.get('blocked')):
            raise ValueError('Source changed or restarted; stop it safely and review switching setup again')

    def validate_prepared(self, record):
        plan = record['source_snapshot']
        if record.get('adopted'):
            if manifest(Path(plan['transcript'])) != plan['manifest']:
                raise ValueError('Original history changed before managed launch; history preserved')
        observed = manifest(Path(record['transcript']),sidecars=Path(record['sidecars']))
        def contents(items):
            return {k:({'directory':True} if v.get('directory') else {'sha256':v['sha256'],'size':v['size']})
                    for k,v in items.items()}
        if contents(observed) != contents(plan['manifest']):
            raise ValueError('Prepared history or sidecars changed; inspect preserved setup before recovery')
        # No slow auth/launch calls may follow this final source check before reservation.
        self._row_unchanged(plan)

    def preview(self, session, names):
        contract = self.shared.proof_contract(names)
        source = self.source(session,names)
        if self.store.read(self.shared.key(source['conversation'])):
            raise ValueError('Conversation is already shared; select its managed session and turn the mode on')
        value = dict(id=str(uuid.uuid4()),expires_at=time.time()+300,profiles=names,
                     contract=contract,accounts=[dict(name=p['name'],label=self.store.get(p['name'])['label'],**p['identity']) for p in contract['profiles']],proof_ready=self.shared.has_proof(contract),**source)
        self.store.write('mode-plan-'+value['id']+'.json',value)
        return value

    def enable(self, token, *, consent=False):
        if not consent: raise ValueError('Explicit consent is required for the selected accounts to access this conversation')
        token = identifier(token)
        with self.store.lock('mode-plan-'+token):
            plan = self.store.read('mode-plan-'+token+'.json')
            if not plan or plan.get('used') or time.time() > plan['expires_at']:
                raise ValueError('Switching setup confirmation expired or was used; review the current conversation again')
            names = plan['profiles']
            if self.shared.require_proof(names) != plan['contract']:
                raise ValueError('Account identities or Claude build changed; review setup again')
            current = self.source(plan['session'],names)
            if any(current[k] != plan[k] for k in current):
                raise ValueError('Source conversation changed after confirmation; review setup again')
            plan['used']=True; self.store.write('mode-plan-'+token+'.json',plan)
            mode = dict(enabled=True,active_index=names.index(plan['source_profile']))
            name = plan['name']+' (switchable)'
            # Already-owned sources use their existing safe move/link implementation.
            binding = self.store.read('bindings.json').get(plan['session'])
            if binding:
                if str(Path(self.store.get(binding['profile'])['directory'])) != plan['directory']:
                    raise ValueError('Owned source directory changed')
                return self.shared.enroll(plan['session'],names,consent=True,mode=mode,name=name,
                                          expected_digest=plan['manifest']['main']['sha256'],mode_plan=plan)
            return self._adopt(plan,mode,name)

    def _adopt(self, plan, mode, name):
        native, names = plan['conversation'], plan['profiles']
        with self.store.lock('transition-'+native):
            if self.store.read(self.shared.key(native)):
                raise ValueError('Conversation already enrolled; select its managed session')
            aliases = []
            for profile_name in names:
                profile = self.store.get(profile_name)
                base = Path(profile['directory'])/'projects'/Path(plan['transcript']).parent.name
                real_directory(base)
                for path in [base/(native+'.jsonl'),base/native]:
                    if path.exists() or path.is_symlink():
                        raise ValueError('An approved account already has this conversation UUID; nothing was overwritten')
                aliases.append(dict(profile=profile_name,transcript=str(base/(native+'.jsonl')),sidecars=str(base/native)))
            folder = self.store.root/'shared'/native
            real_directory(folder.parent)
            if folder.exists() or folder.is_symlink():
                raise ValueError('Previous setup requires recovery; history was preserved')
            private_dir(folder)
            record = dict(conversation=native,project=Path(plan['transcript']).parent.name,cwd=plan['cwd'],name=name,
                transcript=str(folder/'main.jsonl'),sidecars=str(folder/'session'),aliases=aliases,profiles=names,
                proof=plan['contract'],index=mode['active_index'],phase='enrolling',allowed_session='',reservation='',
                original_session=plan['session'],original_sha256=plan['manifest']['main']['sha256'],
                mode=mode,adopted=True,source_snapshot=plan)
            self.shared.save(record)  # Durable recovery before the first snapshot write.
            try:
                source = Path(plan['transcript'])
                (folder/'session').mkdir(mode=0o700)
                for key, item in plan['manifest'].items():
                    destination = folder/'main.jsonl' if key == 'main' else folder/key
                    origin = source if key == 'main' else source.with_suffix('')/key.removeprefix('session/')
                    if item.get('directory'):
                        destination.mkdir(mode=0o700,parents=True,exist_ok=True)
                    else:
                        content, observed = read_file(origin)
                        if observed != item: raise ValueError('Source history changed during snapshot')
                        destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        descriptor = os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                        with os.fdopen(descriptor,'wb') as stream:
                            stream.write(content); stream.flush(); os.fsync(stream.fileno())
                self._unchanged(plan)
                for alias in aliases:
                    Path(alias['transcript']).symlink_to(record['transcript'])
                    Path(alias['sidecars']).symlink_to(record['sidecars'],target_is_directory=True)
                self._unchanged(plan)
                record['phase']='stopped'; self.shared.save(record)
                self.shared.validate(record)
                return self.shared._launch(record,record['index'])
            except BaseException:
                record['phase']='failed'; self.shared.save(record)
                raise

    def _unchanged(self, plan):
        current = self.source(plan['session'],plan['profiles'])
        if any(current[k] != plan[k] for k in current):
            raise ValueError('Source changed while preparing switching; history preserved for inspection')

    def set_enabled(self, session, enabled):
        row = self.tb.call('session','get',session)
        native = identifier(row['agent_session_id'])
        with self.store.lock('transition-'+identifier(native)):
            record = self.shared.load(native)
            if (row.get('id') != record['allowed_session'] or row.get('agent') != 'claude-accounts'
                    or row.get('cwd') != record.get('primary_cwd',record['cwd']) or row.get('host')
                    or row.get('backend_type') not in {None,'tmux','local:tmux'}):
                raise ValueError('Select the current managed conversation before changing its mode')
            if record['phase'] != 'active':
                raise ValueError('Recover the failed transition before changing the switching mode')
            self.shared.validate(record)
            if enabled: self.shared.require_proof(record['profiles'])
            runtime = self.shared._runtime(native)
            if runtime.get('uncertain') or runtime.get('error'):
                raise ValueError('Inspect recovery evidence before changing the switching mode')
            record['mode']=dict(enabled=bool(enabled),active_index=record['index'])
            self.shared.save(record)
            return dict(conversation=native,session=record['allowed_session'],enabled=bool(enabled))
