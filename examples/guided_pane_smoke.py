"""Exercise the guided Lua pane in a real isolated Thurbox VM; no auth/model calls."""
import fcntl
import json
import os
from pathlib import Path
import pty
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thurbox_accounts.accounts_ui import install


def main():
    root = Path(tempfile.mkdtemp(prefix='tbx-guided-', dir='/tmp')).resolve()
    config = root / 'config'; config.mkdir()
    os.environ.update(THURBOX_CONFIG_DIR=str(config), THURBOX_DATA_DIR=str(root/'data'),
                     THURBOX_SOCKET='tbx-guided-'+uuid.uuid4().hex[:12])
    (config/'settings.toml').write_text('[features]\nauto_update=false\nversion_check=false\nautomations=false\nnotifications=false\n')
    cli = str(Path.home()/'.local/bin/thurbox-cli')
    def call(*args):
        r = subprocess.run([cli, *args, '--json'], text=True, capture_output=True, timeout=15)
        if r.returncode: raise AssertionError(r.stderr or r.stdout)
        return json.loads(r.stdout)
    call('plugin', 'new', 'accounts')
    installed = install(cli, root/'accounts', '/fixture/no-claude')
    path = Path(installed['pane'])
    source = path.read_text()
    # A VM fixture, not trusted capabilities: no child process is ever launched.
    source = 'local run = function(key, cmd, opts) if key:match("^accounts%-operation") then state.test_command = cmd end end\n' + source
    source = source.replace('local function result() return (thurbox.runs or {})[state.request_key or "none"] end',
        'local function result() if state.request_key then return {state="done",ok=true,stdout="Fixture complete"} end end')
    source = source.replace('local answer = (thurbox.runs or {})[data_key()]',
        'local answer = {state="done",ok=true,stdout=state.test_fixture or ""}')
    rows = [['account','work-a','Work A','a@example.invalid','saved'], ['account','work-b','Work B','b@example.invalid','saved']]
    for i in range(4): rows.append(['conversation','fixture-'+str(i),'Project '+str(i),'work-a','single','','/fixture/project','stopped','fixture-native-'+str(i),''])
    fixture = '\n'.join('\t'.join(quote(s,safe='') for s in row) for row in rows)
    source = source.replace('dispatch = function(id)', 'dispatch = function(id)\n  if id == "accounts.test-populated" then state.test_fixture = '+json.dumps(fixture)+'; state.request_key=nil; state.test_command=nil; state.screen="accounts"; state.focus=1; return true end\n  if id == "accounts.test-login" then state.login_profile="work-a"; return true end\n  if id == "accounts.test-added" then state.account="work-a"; state.added_label="Work B"; return true end')
    source = source.replace('local function projects()','local function projects() if state.test_fixture then return {"/fixture/one","/fixture/two","/fixture/three"} end')
    source = source.replace('return ui.panel({ title = "Claude Accounts", focused = ctx.focused, body = children })', 'local y=1; for _, node in ipairs(children) do if node.id=="create" then state.test_create_row=y end; if node.id=="new-form" and state.new_form then state.test_cancel_row=y end; y=y+(node.len or 0) end; state.test_height=ctx.height; return ui.panel({ title = "Claude Accounts", focused = ctx.focused, body = children })')
    source = source.replace('on_action = dispatch,' , 'on_action = dispatch, ui_state = function() return {focus=state.focus, test_command=state.test_command and state.test_command:sub(-230), sharing=table.concat(state.sharing or {}, ","), pending=state.pending and state.pending.kind, profiles=state.pending and table.concat(state.pending.profiles, ","), login_profile=state.login_profile, nickname=state.nickname and state.nickname.value, create_row=state.test_create_row, cancel_row=state.test_cancel_row, height=state.test_height, selected=account(model()) and account(model()).name} end,')
    source = source.replace('commands = {', 'commands = {\n    {action="accounts.test-populated",desc="Fixture"},\n    {action="accounts.test-login",desc="Fixture login"},\n    {action="accounts.test-added",desc="Fixture added"},')
    path.write_text(source)
    assert call('plugin','check')['ok']
    master, slave = pty.openpty()
    def resize(rows, cols=80):
        fcntl.ioctl(master, __import__('termios').TIOCSWINSZ, struct.pack('HHHH',rows,cols,0,0))
    resize(24)
    process = subprocess.Popen([str(Path.home()/'.local/bin/thurbox')], stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = bytearray()
    def drain():
        try:
            while True: output.extend(os.read(master,65536))
        except OSError: pass
    threading.Thread(target=drain,daemon=True).start()
    def state(): return call('ui','state')
    def pane():
        snap = state()
        return snap.get('plugin_state',{}).get('plugins/90_accounts.lua',{})
    def action(name):
        call('ui','action','accounts.'+name); time.sleep(.15)
    def key(name):
        os.write(master, {'tab':b'\t','enter':b'\r'}[name]); time.sleep(.15)
    try:
        for _ in range(60):
            try:
                state(); break
            except AssertionError: time.sleep(.1)
        os.write(master,b'\x1b[18~'); time.sleep(.3)
        (root/'initial-state.json').write_text(json.dumps(state(),indent=2))
        key('tab'); key('tab')
        os.write(master,b'Work A'); time.sleep(.2)
        action('add')
        assert "'pane-add' 'Work A'" in pane().get('test_command',''), pane()
        action('test-populated'); action('test-added'); assert pane()['selected']=='work-b'
        action('conversations'); action('sharing')
        key('tab'); key('tab'); key('enter'); key('tab'); key('enter')
        assert pane()['sharing'] == 'work-a,work-b', pane()
        action('verify'); assert pane()['pending']=='verify' and not pane().get('test_command')
        action('cancel'); assert not pane().get('pending') and not pane().get('test_command')
        action('enable'); assert pane()['profiles']=='work-a,work-b'
        resize(10); os.kill(process.pid,signal.SIGWINCH); time.sleep(.3)
        action('confirm'); assert pane().get('pending') and not pane().get('test_command')
        resize(24); os.kill(process.pid,signal.SIGWINCH); time.sleep(.3)
        action('confirm'); assert "'enable-shared' '--session' 'fixture-0' '--consent'" in pane()['test_command']
        action('test-login'); os.write(master,b'\x1b[18~'); time.sleep(.3)
        assert not pane().get('login_profile'), pane()
        action('new-form')
        resize(20); os.kill(process.pid,signal.SIGWINCH); time.sleep(.3)
        assert pane()['create_row'] <= pane()['height']-2, pane()
        assert pane()['cancel_row'] <= pane()['height']-2, pane()
        (root/'terminal.bin').write_bytes(output)
        assert not (config/'ui.json').exists() or not json.loads((config/'ui.json').read_text()).get('trusted')
        print(json.dumps(dict(ok=True, artifacts=str(root), real_tui=True, fake_operations=True,
            keyboard_add=True, explicit_confirmation=True, small_confirmation_blocked=True, login_f7_back=True)))
    finally:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
        os.close(master)
        subprocess.run([cli,'runtime','stop'],capture_output=True,timeout=10)

if __name__=='__main__': main()
