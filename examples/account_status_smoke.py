"""Real isolated Lua/TUI account-strip checks; no auth, trust or model requests."""
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
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thurbox_accounts.accounts_ui import install


def main():
    root = Path(tempfile.mkdtemp(prefix='tbx-account-status-', dir='/tmp')).resolve()
    config = root/'config'; config.mkdir()
    os.environ.update(THURBOX_CONFIG_DIR=str(config), THURBOX_DATA_DIR=str(root/'data'),
                     THURBOX_SOCKET='tbx-status-'+uuid.uuid4().hex[:12])
    (config/'settings.toml').write_text('[features]\nauto_update=false\nversion_check=false\nautomations=false\nnotifications=false\n')
    cli = str(Path.home()/'.local/bin/thurbox-cli')
    def call(*args):
        result = subprocess.run([cli,*args,'--json'],capture_output=True,text=True,timeout=15)
        if result.returncode: raise AssertionError(result.stderr or result.stdout)
        return json.loads(result.stdout)
    call('plugin','new','accounts')
    installed = install(cli,root/'accounts','/fixture/no-claude')
    path = Path(installed['indicator'])
    source = path.read_text()
    # Substitute read-only fixture snapshots inside this test copy of the VM.
    source = source.replace('local selected = store.selected','local selected = "selected"; if state.fixture == "none" then selected = nil end')
    source = source.replace('for _, row in ipairs(thurbox.sessions or {}) do if row.id == selected then session = row; break end end',
        'session = { id="selected", agent=state.fixture == "codex" and "codex" or "claude" }')
    source = source.replace('local answer = (thurbox.runs or {})[key]',
        'local answer = state.fixture ~= "loading" and {state="done",ok=state.fixture ~= "error",stdout="indicator\\tselected\\tclaude\\t" .. (state.fixture == "b" and "Enterprise%20B" or "Enterprise%20A") .. "\\trunning"} or nil')
    source = source.replace('capabilities = { "run" },', 'capabilities = { "run" },\n  commands={{action="status.codex",desc="Test"},{action="status.a",desc="Test"},{action="status.b",desc="Test"},{action="status.loading",desc="Test"},{action="status.error",desc="Test"},{action="status.none",desc="Test"}},\n  on_action=function(action) state.fixture=action:match("status%.(.+)"); return true end,')
    # Fixture run exists only in this copy. It never starts a child process.
    path.write_text('local run = function() end\n'+source)
    assert call('plugin','check')['ok']
    master, slave = pty.openpty()
    fcntl.ioctl(master,__import__('termios').TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
    process = subprocess.Popen([str(Path.home()/'.local/bin/thurbox')],stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
    os.close(slave)
    output = bytearray()
    def drain():
        try:
            while True: output.extend(os.read(master,65536))
        except OSError: pass
    threading.Thread(target=drain,daemon=True).start()
    def state(): return call('ui','state')
    def label(): return state().get('plugin_state',{}).get('plugins/91_account_status.lua',{}).get('label')
    try:
        for _ in range(60):
            try:
                if label(): break
            except AssertionError: pass
            time.sleep(.1)
        for fixture, expected in [('codex','Account: default | Codex'),('a','Account: Enterprise A | running | F7 Accounts'),
                                  ('b','Account: Enterprise B | running | F7 Accounts'),('loading','Account: checking…'),
                                  ('error','Account: unavailable | F7 for Accounts'),('none','Account: no conversation selected')]:
            call('ui','action','status.'+fixture)
            time.sleep(.2)
            assert label() == expected, (fixture,label())
        # The strip is present while Agent is focused, without opening Accounts.
        snapshot = state()
        assert snapshot['focused_pane']=='agent', snapshot
        strip=next(slot for slot in snapshot['slots'] if slot['slot']=='account-status')
        assert strip['shown'] and strip['rect']['height']==1 and 'account-status' in strip['visible_panes'], strip
        (root/'state.json').write_text(json.dumps(snapshot,indent=2))
        (root/'terminal.bin').write_bytes(output)
        print(json.dumps(dict(ok=True,artifacts=str(root),real_tui=True,codex_default=True,account_changes=True,loading_and_failure=True)))
    finally:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
        os.close(master)
        subprocess.run([cli,'runtime','stop'],capture_output=True,timeout=10)

if __name__ == '__main__': main()
