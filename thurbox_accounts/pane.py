"""Friendly terminal-pane display transport; all policy remains in Accounts/Shared."""
import re
import unicodedata
from urllib.parse import quote

from .desktop import Desktop

OPERATIONS = {'pane-add','status','start','desktop-stop','desktop-start',
              'verify-shared','enable-shared','switch','recover-shared'}


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


def snapshot(accounts):
    data = Desktop(accounts).state()
    lines = []
    def row(*values):
        lines.append('\t'.join(quote(str(value),safe='') for value in values))
    for profile in data['profiles']:
        row('account',profile['name'],profile['label'],profile['email'],
            'saved' if profile['email'] != 'Login required' else 'login')
    for item in data['conversations']:
        row('conversation',item['id'],item['name'],item['profile'],
            'shared' if item['shared'] else 'single',item.get('next_profile',''),item['cwd'],
            'stopped' if item['stopped'] else 'running',item.get('conversation',''),item['phase'])
    proof = accounts.profiles.read('shared-proof.json')
    if proof:
        row('proof',','.join(p['name'] for p in proof.get('profiles',[])))
    return '\n'.join(lines)


def receipt(action, value):
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
