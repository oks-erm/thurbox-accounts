"""Friendly terminal-pane display transport; all policy remains in Accounts/Shared."""
import re
import unicodedata
from urllib.parse import quote

from .desktop import Desktop

OPERATIONS = {'pane-add','status','start','desktop-stop','desktop-start',
              'verify-shared','enable-shared','switch','recover-shared',
              'mode-preview','mode-enable','mode-on','mode-off'}


def add(store, label):
    label = label.strip()
    if not label or len(label) > 60 or any(ord(char) < 32 for char in label):
        raise ValueError('Enter an account name between 1 and 60 characters, for example Work A')
    # The registry lock in Profiles.add still arbitrates competing creates.
    existing = store.read('profiles.json')
    if any(p['label'].casefold() == label.casefold() for p in existing.values()):
        raise ValueError('An account with this name already exists. Select it and click Log in.')
    ascii_label = unicodedata.normalize('NFKD',label).encode('ascii','ignore').decode().lower()
    base = re.sub('[^a-z0-9]+','-',ascii_label).strip('-')[:40] or 'account'
    name, suffix = base, 2
    while name in existing:
        name = base + '-' + str(suffix)
        suffix += 1
    return store.add(name,label)


def snapshot(accounts, session=None):
    data = Desktop(accounts).state()
    lines = []
    def row(*values):
        lines.append('\t'.join(quote(str(value),safe='') for value in values))
    for profile in data['profiles']:
        row('account',profile['name'],profile['label'],profile['email'],
            'saved' if profile['email'] != 'Login required' else 'login')
    records = Desktop(accounts).records()
    # Older records did not preserve a confirmed index during failed switches.
    for item in data['conversations']:
        if item['shared'] and item['phase'] != 'active' and records.get(item['id'],{}).get('mode',{}).get('active_index') is None:
            item['profile'] = ''
    current_id = session
    if session:
        # Originals and stale owners map to their current guarded conversation.
        selected = accounts.thurbox.call('session','get',session)
        supported = (not selected.get('host') and selected.get('backend_type') in {None,'tmux','local:tmux'}
                     and selected.get('agent') in {'claude','claude-accounts'})
        record = next((r for r in records.values() if supported and ( r['conversation']==selected.get('agent_session_id')
                       or r.get('original_session')==session)),None)
        if record:
            current_id = record.get('allowed_session') or 'pending:'+record['conversation']
        elif not any(c['id']==session for c in data['conversations']):
            local = not selected.get('host') and selected.get('backend_type') in {None,'tmux','local:tmux'}
            if selected.get('agent')=='claude' and local:
                data['conversations'].insert(0,dict(id=selected['id'],name=selected.get('name',selected['id']),profile='',
                    cwd=selected['cwd'],shared=False,stopped=bool(selected.get('stopped')),phase='ordinary',external=True))
            else:
                row('unsupported',session,'Select a local Claude conversation in WSL to use switching mode.')
        row('current',current_id)
        row('indicator',*indicator(accounts,selected,data,records))
    for item in data['conversations']:
        row('conversation',item['id'],item['name'],item['profile'],
            'shared' if item['shared'] else 'single',item.get('next_profile',''),item['cwd'],
            'stopped' if item['stopped'] else 'running',item.get('conversation',''),item['phase'],
            'off' if not item['shared'] or records.get(item['id'],{}).get('mode',{}).get('enabled') is False else 'on',
            'external' if item.get('external') else 'owned')
    proof = accounts.profiles.read('shared-proof.json')
    if proof:
        row('proof',','.join(p['name'] for p in proof.get('profiles',[])))
    return '\n'.join(lines)


def indicator(accounts, selected, data, records):
    """Read-only label for the actual selected session, never the login picker."""
    agent = selected.get('agent') or 'unknown'
    status = 'stopped' if selected.get('stopped') else 'running'
    label = 'default' if agent == 'codex' else 'unverified'
    local = not selected.get('host') and selected.get('backend_type') in {None, 'tmux', 'local:tmux'}
    item = next((c for c in data['conversations'] if c['id'] == selected['id']), None)
    binding = accounts.profiles.read('bindings.json').get(selected['id'], {})
    record = records.get(selected['id'], {})
    matched = local and selected.get('cwd') == (record or binding).get('cwd')
    if item and item['shared'] and item['phase'] != 'active':
        status = 'recovery needed'
    if item and item.get('profile') and matched:
        native = selected.get('agent_session_id')
        confirmed = (agent == 'claude-accounts' and native and native == record.get('conversation')
                     or agent == 'claude' and native and native == binding.get('agent_session_id'))
        if confirmed:
            label = next((p['label'] for p in data['profiles'] if p['name'] == item['profile']), item['profile'])
            if item['shared'] and item['phase'] != 'active':
                status = 'last confirmed (recovery needed)'
    return selected['id'], agent, label, status


def receipt(action, value):
    if action == 'mode-preview':
        def encoded(*values): return '\t'.join(quote(str(v),safe='') for v in values)
        lines = [encoded('mode-plan',value['id'],value['session'],value['conversation'],value['name'],
                         value['source_profile'],value['expires_at'],'ready' if value['proof_ready'] else 'missing')]
        for account in value['accounts']:
            lines.append(encoded('mode-account',account['name'],account['label'],account['email'],account.get('orgId','Organization not reported')))
        return '\n'.join(lines)
    if action == 'mode-enable':
        return 'Switching mode is On. Continue this conversation or click its named Switch to button.'
    if action == 'mode-on': return 'Switching mode is On. The approved accounts are available again.'
    if action == 'mode-off': return 'Switching mode is Off. The current account and history are retained.'
    if action == 'pane-add':
        return 'Account added. Select it and click Log in to connect it to Claude.'
    if action == 'status':
        return ('Signed in as ' + value.get('email','this account') + '.' if value.get('loggedIn') else
                'This account is not connected yet. Click Log in and finish the browser sign-in.')
    if action == 'start':
        return 'Conversation created. Select it below and click Open conversation.'
    if action == 'verify-shared':
        return 'Compatibility check passed. You can now enable switching for the stopped conversation.'
    if action == 'enable-shared':
        return 'Switching enabled. The same conversation is ready under the current account.'
    if action == 'switch':
        return value.get('notice') or 'Switched to ' + value['profile'] + '. Click Open conversation to continue.'
    if action == 'recover-shared':
        return 'Conversation recovered. Select it below and continue.'
    if action == 'desktop-stop':
        return 'Conversation stopped. Its history is retained.'
    if action == 'desktop-start':
        return 'Conversation resumed. Click Open conversation to continue.'
    return value.get('notice') or 'Done.'
