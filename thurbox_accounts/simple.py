"""Named guarded starts and explicit inline account switching; native owns auth."""
import argparse
import os
from pathlib import Path
import time
import uuid

from .accounts import Accounts, Claude, Profiles, private_dir
from .shared import Shared, identifier, real_directory
from .thurbox import Thurbox


def agent_name(profile):
    return 'Claude — ' + profile['label']


class Simple:
    def __init__(self, accounts):
        self.accounts=accounts; self.store=accounts.profiles; self.tb=accounts.thurbox
        self.shared=Shared(accounts)

    def row(self, record):
        row=self.tb.call('session','get',record['allowed_session'])
        expected_agent=record['source_agent'] if record.get('kind')=='single' else 'claude-accounts'
        if (row.get('agent') != expected_agent or row.get('agent_session_id') != record['conversation']
                or row.get('cwd') != record.get('primary_cwd',record['cwd']) or row.get('host')
                or row.get('backend_type') not in {None,'tmux','local:tmux'}):
            raise ValueError('Conversation identity, UUID, owner or local backend changed')
        return row

    def validate_single(self, record):
        names=record.get('profiles',[])
        if len(names)!=1 or record.get('index')!=0 or record.get('phase')!='active':
            raise ValueError('Single-account session identity or phase changed')
        profile=self.store.get(names[0])
        if (record.get('identity') != profile.get('identity') or record.get('source_agent') != agent_name(profile)
                or Path(record['transcript']) != self.store.root/'shared'/identifier(record['conversation'])/'main.jsonl'):
            raise ValueError('Single-account profile identity changed')
        folder=Path(record['transcript']).parent
        private_dir(folder)

    def bootstrap(self, name, args, owner, cwd):
        profile=self.accounts.authenticated(name)
        self.accounts.check_launch(profile)
        identifiers=[args[i+1] for i,a in enumerate(args[:-1]) if a in {'--session-id','--resume','-r'}]
        if len(identifiers)!=1 or any(a in args for a in ('--fork-session','--continue','-c')):
            raise ValueError('Named account launch requires exactly one pinned native UUID; fork/continue is unsupported')
        native=identifier(identifiers[0]); owner=identifier(owner); cwd=Path(cwd).resolve(strict=True)
        row=self.tb.call('session','get',owner)
        if row.get('agent') != agent_name(profile) or row.get('agent_session_id') != native:
            raise ValueError('Named profile launch identity or UUID changed')
        directories=[]
        for i,arg in enumerate(args):
            if arg=='--add-dir':
                if i+1>=len(args): raise ValueError('Missing additional directory')
                value=Path(args[i+1]).expanduser()
                value=(cwd/value).resolve(strict=True) if not value.is_absolute() else value.resolve(strict=True)
                if not value.is_dir(): raise ValueError('Additional directory must be a directory')
                directories.append(str(value))
        record=dict(native_dirs=directories,kind='single',conversation=native,profiles=[name],identity=profile['identity'],
                    source_agent=agent_name(profile),cwd=str(cwd),primary_cwd=row.get('cwd'),
                    transcript=str(self.store.root/'shared'/native/'main.jsonl'),
                    index=0,phase='active',allowed_session=owner,reservation='',name=row.get('name',owner))
        self.row(record)
        with self.store.lock('transition-'+native):
            existing=self.store.read(self.shared.key(native))
            if existing:
                if existing.get('kind')!='single' or existing.get('allowed_session')!=owner:
                    raise ValueError('This owner was replaced by a shared session; use the current conversation')
                if any(existing.get(k)!=record.get(k) for k in record if k!='name'):
                    raise ValueError('Named session profile or identity changed')
                self.validate_single(existing)
                if existing.get('name')!=record['name']:
                    existing['name']=record['name']; self.shared.save(existing)
                return existing
            self.validate_single(record)
            with self.store.lock():
                bindings=self.store.read('bindings.json')
                expected=dict(profile=name,identity=profile['identity'],cwd=row['cwd'],agent_session_id=native,agent=record['source_agent'])
                if owner in bindings and bindings[owner]!=expected:
                    raise ValueError('Session already has a different account binding')
                bindings[owner]=expected
                self.store.write('bindings.json',bindings)
                self.shared.save(record)
        return record

    def transcript(self, record):
        profile=self.store.get(record['profiles'][0])
        projects=Path(profile['directory'])/'projects'
        if not projects.exists(): return None
        from .mode import checked
        checked(projects,directory=True)
        found=[]
        for i,folder in enumerate(projects.iterdir()):
            if i>=2000: raise ValueError('Too many native project directories to locate this conversation safely')
            if folder.is_symlink(): continue
            candidate=folder/(record['conversation']+'.jsonl')
            if candidate.exists() or candidate.is_symlink(): found.append(candidate)
        if len(found)>1: raise ValueError('Native conversation UUID is ambiguous across project directories')
        return found[0] if found else None

    def source(self, session):
        from .guard import writer_available
        from .mode import checked, manifest
        row=self.tb.call('session','get',session)
        record=self.shared.load(identifier(row['agent_session_id']))
        if record.get('kind')!='single' or record.get('allowed_session')!=row['id']:
            raise ValueError('Select the current named-account session')
        self.validate_single(record); self.row(record)
        runtime=self.shared._runtime(record['conversation'])
        if (row.get('stopped') is not True or runtime.get('phase')!='stopped' or runtime.get('native_pid')
                or any(runtime.get(k) for k in ('tools','subagents','background_tools','blocked','uncertain','error'))
                or not writer_available(self.store,record['conversation'])):
            raise ValueError('Named source has not confirmed safe shutdown')
        binding=self.store.read('bindings.json').get(session,{})
        profile=self.accounts.authenticated(record['profiles'][0])
        if binding.get('profile')!=profile['name'] or binding.get('identity')!=profile['identity']:
            raise ValueError('Named source profile binding changed')
        path=Path(row.get('transcript_path') or self.transcript(record) or '')
        checked(path)
        if path.name!=record['conversation']+'.jsonl' or path.parent.parent!=Path(profile['directory'])/'projects':
            raise ValueError('Named source history is outside its account directory')
        files=manifest(path)
        return row,binding,path,files['main']['sha256']

    def _selection(self, session, target):
        row=self.tb.call('session','get',session)
        record=self.shared.load(identifier(row['agent_session_id']))
        if record.get('allowed_session')!=row['id'] or record.get('phase')!='active':
            raise ValueError('Conversation owner changed or needs recovery')
        self.row(record); self.shared.validate(record)
        if record.get('kind')!='single' and record.get('mode',{}).get('enabled') is False:
            raise ValueError('Switching is Off for this conversation')
        current=record['profiles'][record['index']]
        if target==current: raise ValueError('This conversation already uses that account')
        names=list(record['profiles'])
        if target not in names: names.append(target)
        if record.get('kind')=='single':
            prepared=self.store.read('shared-proof.json').get('profiles',[])
            prepared_names=[p['name'] for p in prepared]
            if len(prepared_names)==len(names) and set(prepared_names)==set(names): names=prepared_names
        contract=self.shared.proof_contract(names)
        if record.get('kind')=='single' and not self.shared.has_proof(contract):
            reverse=list(reversed(names)); reverse_contract=self.shared.proof_contract(reverse)
            if self.shared.has_proof(reverse_contract): names,contract=reverse,reverse_contract
        for p in names: self.accounts.check_launch(self.store.get(p))
        snapshot={k:record.get(k) for k in ('conversation','allowed_session','kind','cwd','primary_cwd','native_dirs','source_agent','identity','index','profiles','mode')}
        return row,record,current,names,contract,snapshot

    def preview(self, session, target):
        row,record,current,names,contract,snapshot=self._selection(session,target)
        approved=record.get('kind')!='single' and target in record['profiles']
        plan=dict(id=str(uuid.uuid4()),expires_at=time.time()+300,session=row['id'],target=target,
                  conversation=record['conversation'],name=record.get('name',row.get('name',row['id'])),
                  source_profile=current,profiles=names,contract=contract,snapshot=snapshot,
                  proof_ready=self.shared.has_proof(contract),approved=approved,
                  accounts=[dict(name=p['name'],label=self.store.get(p['name'])['label'],**p['identity']) for p in contract['profiles']])
        self.store.write('simple-plan-'+plan['id']+'.json',plan)
        return plan

    def select(self, session, target):
        plan=self.preview(session,target)
        if plan['approved'] and plan['proof_ready']:
            return dict(completed=True,**self.confirm(plan['id'],consent=True))
        return plan

    def confirm(self, token, *, consent=False):
        if not consent: raise ValueError('Explicit consent is required to switch this conversation')
        token=identifier(token)
        with self.store.lock('simple-plan-'+token):
            plan=self.store.read('simple-plan-'+token+'.json')
            if not plan or plan.get('used') or time.time()>plan['expires_at']:
                raise ValueError('Switch confirmation expired or was used; choose the account again')
            with self.store.lock('transition-'+plan['conversation']):
                row,record,current,names,contract,snapshot=self._selection(plan['session'],plan['target'])
                if snapshot!=plan['snapshot'] or contract!=plan['contract']:
                    raise ValueError('Conversation owner or account identities changed; review again')
                self.shared.require_proof(names)
                # No source shutdown before proof, identities and launch checks succeed.
                if record.get('kind')=='single':
                    self._preflight_history(row,record,names)
                elif names!=record['profiles']:
                    self._extension_aliases(record,names)  # collision check before pause
                self.row(record)
                plan['used']=True; self.store.write('simple-plan-'+token+'.json',plan)
                self.shared._pause(record,allow_idle=True)
                if record.get('kind')=='single':
                    result=self.shared.enroll(row['id'],names,consent=True,launch=False,
                        mode=dict(enabled=True,active_index=names.index(current)),name=record.get('name'),guarded_source=True,transition_held=True)
                    return self.shared._launch(result,names.index(plan['target']))
                if names!=record['profiles']:
                    self._extend(record,names,contract)
                return self.shared._launch(record,names.index(plan['target']))

    def _preflight_history(self, row, record, names):
        path=Path(row.get('transcript_path') or self.transcript(record) or '')
        if not path.is_absolute() or not path.is_file():
            raise ValueError('Send the first message before switching; no native history exists yet')
        for name in names:
            if name==record['profiles'][0]: continue
            base=Path(self.store.get(name)['directory'])/'projects'/path.parent.name
            for candidate in (base/path.name,base/record['conversation']):
                if candidate.exists() or candidate.is_symlink():
                    raise ValueError('Target already has this conversation UUID; nothing was overwritten')

    def _extension_aliases(self, record, names):
        aliases=[]
        for name in names:
            if name in record['profiles']: continue
            base=Path(self.store.get(name)['directory'])/'projects'/record['project']
            real_directory(base)
            alias=dict(profile=name,transcript=str(base/(record['conversation']+'.jsonl')),sidecars=str(base/record['conversation']))
            if any(Path(alias[k]).exists() or Path(alias[k]).is_symlink() for k in ('transcript','sidecars')):
                raise ValueError('Target already has this conversation UUID; nothing was overwritten')
            aliases.append(alias)
        return aliases

    def _extend(self, record, names, contract):
        self.shared.validate(record)
        aliases=self._extension_aliases(record,names)
        record.update(profiles=names,proof=contract,phase='enrolling',aliases=record['aliases']+aliases)
        self.shared.save(record)  # Recovery evidence before cross-account aliases.
        try:
            for alias in aliases:
                Path(alias['transcript']).symlink_to(record['transcript'])
                Path(alias['sidecars']).symlink_to(record['sidecars'],target_is_directory=True)
            record['phase']='active'; self.shared.save(record); self.shared.validate(record)
        except BaseException:
            record['phase']='failed'; self.shared.save(record); raise


def run_profile(argv):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--account-profile',required=True); parser.add_argument('--account-root',type=Path,required=True)
    parser.add_argument('--account-claude',required=True); parser.add_argument('--account-cli',required=True)
    options,args=parser.parse_known_args(argv)
    accounts=Accounts(Profiles(options.account_root),Claude(options.account_claude),Thurbox([options.account_cli]))
    owner=os.environ.get('THURBOX_SESSION','')
    # Native starts before Thurbox persists its row. Wait for the public row;
    # nothing authenticates or launches before its immutable identity is known.
    deadline=time.monotonic()+30
    while True:
        try: accounts.thurbox.call('session','get',owner); break
        except RuntimeError:
            if time.monotonic()>=deadline: raise ValueError('Thurbox did not persist this session; native Claude was not started')
            time.sleep(.1)
    record=Simple(accounts).bootstrap(options.account_profile,args,owner,Path.cwd())
    os.environ.update(THURBOX_ACCOUNTS_ROOT=str(accounts.profiles.root),THURBOX_ACCOUNTS_CONVERSATION=record['conversation'],
                      THURBOX_ACCOUNTS_CLAUDE=options.account_claude,THURBOX_ACCOUNTS_PROFILE=options.account_profile,
                      THURBOX_ACCOUNTS_CLI=options.account_cli)
    from .guard import main
    return main(args)
