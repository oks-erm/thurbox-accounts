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
