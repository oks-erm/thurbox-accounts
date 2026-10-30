"""Add one absolute guarded agent definition; preserve all existing agent edits."""
import json
from pathlib import Path
import shutil
import time
import tomllib

from .core import atomic_write
from .shared import AGENT


def register(thurbox, launcher):
    if not launcher.is_file():
        raise ValueError('Guarded launcher was not delivered by the extension')
    thurbox.call('agent','launch-args','claude')  # Ensure the registry is seeded.
    paths = thurbox.call('config','show').get('paths',{})
    path = Path(paths.get('agents_toml',''))
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Cannot safely locate the Thurbox agent registry')
    definition = dict(name=AGENT,command=str(launcher),args=[],resume_args=['--resume','{id}'],
        new_session_args=['--session-id','{id}'],additional_dir_args=['--add-dir','{dir}'],hook_schema='claude')
    text = path.read_text()
    values = tomllib.loads(text)
    existing = next((a for a in values.get('agents',[]) if a.get('name') == AGENT),None)
    if existing:
        # Thurbox's hook reconciler appends its own native hook-only settings.
        # Accept that exact additive patch on rerun without rewriting the entry.
        expected = dict(definition)
        native_hooks = path.parent / 'hooks/claude.json'
        if existing.get('args') == ['--settings',str(native_hooks)]:
            from .guard import guarded_settings
            guarded_settings(existing['args'],launcher)
            expected['args'] = existing['args']
        if any(existing.get(key) != value for key,value in expected.items()):
            raise ValueError('Existing claude-accounts agent has custom edits; preserved, registration refused')
        return dict(agent=AGENT,added=False)
    block = '\n[[agents]]\n' + '\n'.join(key + ' = ' + json.dumps(value,ensure_ascii=False) for key,value in definition.items()) + '\n'
    # JSON scalars/arrays used here are valid TOML; never rewrite the rest.
    backup = path.with_name(path.name + '.accounts-backup.' + str(time.time_ns()))
    shutil.copy2(path,backup)
    atomic_write(path,text.rstrip()+'\n'+block)
    return dict(agent=AGENT,added=True,backup=str(backup))


def register_profiles(accounts, launcher):
    """Add named account choices without touching native/default definitions."""
    from .simple import agent_name
    if not launcher.is_file(): raise ValueError('Named launcher is missing')
    tb=accounts.thurbox
    tb.call('agent','launch-args','claude')
    path=Path(tb.call('config','show').get('paths',{}).get('agents_toml',''))
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Cannot safely locate the Thurbox agent registry')
    command=tb.command[0] if getattr(tb,'command',None) else 'thurbox-cli'
    text=path.read_text(); existing=tomllib.loads(text).get('agents',[]); additions=[]; names=[]
    labels=set()
    for key in accounts.profiles.read('profiles.json'):
        profile=accounts.profiles.get(key)
        if not profile.get('identity'): continue
        label=profile['label'].casefold()
        if label in labels: raise ValueError('Account labels must be distinct; duplicate named-account choices were not registered')
        labels.add(label)
    for key in accounts.profiles.read('profiles.json'):
        p=accounts.profiles.get(key)
        if not p.get('identity'): continue
        name=agent_name(p); names.append(name)
        definition=dict(name=name,command=str(launcher),args=['--account-profile',key,'--account-root',str(accounts.profiles.root),
                        '--account-claude',accounts.claude.executable,'--account-cli',command],
                        resume_args=['--resume','{id}'],new_session_args=['--session-id','{id}'],
                        additional_dir_args=['--add-dir','{dir}'],hook_schema='claude')
        old=next((a for a in existing if a.get('name')==name),None)
        if old:
            expected=dict(definition)
            native_hooks=path.parent/'hooks/claude.json'
            if old.get('args')==definition['args']+['--settings',str(native_hooks)]:
                from .guard import guarded_settings
                guarded_settings(['--settings',str(native_hooks)],launcher)
                expected['args']=old['args']
            if any(old.get(k)!=v for k,v in expected.items()):
                raise ValueError('Existing named account agent has custom edits; preserved: '+name)
        else:
            additions.append('\n[[agents]]\n'+'\n'.join(k+' = '+json.dumps(v,ensure_ascii=False) for k,v in definition.items())+'\n')
    if additions:
        backup=path.with_name(path.name+'.accounts-backup.'+str(time.time_ns())); shutil.copy2(path,backup)
        atomic_write(path,text.rstrip()+'\n'+''.join(additions))
    return dict(agents=names,added=len(additions))
