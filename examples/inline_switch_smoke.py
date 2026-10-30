"""Real Ctrl+N/inline Lua UI smoke; synthetic snapshots, no grants/auth/models."""
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

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from thurbox_accounts.accounts_ui import install
from thurbox_accounts.pane import receipt


def main():
    root=Path(tempfile.mkdtemp(prefix='tbx-inline-',dir='/tmp')).resolve(); config=root/'config'; config.mkdir()
    os.environ.update(THURBOX_CONFIG_DIR=str(config),THURBOX_DATA_DIR=str(root/'data'),THURBOX_SOCKET='tbx-inline-'+uuid.uuid4().hex[:12])
    (config/'settings.toml').write_text('[features]\nauto_update=false\nversion_check=false\nautomations=false\nnotifications=false\n')
    definitions=['config_version=1','default="claude"']
    for name in ('claude','codex','claude-accounts','Claude — Work A','Claude — Work B'):
        definitions += ['[[agents]]','name='+json.dumps(name),'command="/bin/cat"']
    (config/'agents.toml').write_text('\n'.join(definitions)+'\n')
    cli=str(Path.home()/'.local/bin/thurbox-cli')
    def call(*args):
        r=subprocess.run([cli,*args,'--json'],capture_output=True,text=True,timeout=15)
        if r.returncode: raise AssertionError(r.stderr or r.stdout)
        return json.loads(r.stdout)
    source_id=call('session','create','--name','inline-fixture','--repo-path',str(root),'--agent','Claude — Work A','--on-existing','fail')['id']
    other_id=call('session','create','--name','other-fixture','--repo-path',str(root),'--agent','Claude — Work B','--on-existing','fail')['id']
    call('config','accept-interface')  # isolated fixture: no v1 migration or trust changes
    call('plugin','new','accounts'); installed=install(cli,root/'accounts','/fixture/no-claude')
    creation=Path(installed['creation']); s=creation.read_text().replace('return thurbox.granted and thurbox.granted.sessions == true','return state.test_permission == true or (thurbox.granted and thurbox.granted.sessions == true)')
    s=s.replace('  commands = {','  commands = {')  # actions below exercise the native existing entry point
    s=s.replace('  on_action = function(action)','''  on_action = function(action)
    if action == "new_session.test-agent" then
      state.test_permission=true; local flow=fresh(); flow.host=""; flow.primary="/fixture/project"; flow.name=textinput.new("Fixture"); flow.step="agent"; save(flow); return true
    end''')
    s=s.replace('  keys = {','  commands={{action="new_session.test-agent",desc="Fixture agent picker"}},\n  keys = {',1)
    s=s.replace('return { open = true, step = flow.step, selection = selection }','local choices={}; for _,a in ipairs(agents()) do choices[#choices+1]=a.name.."="..a.command end; return {open=true,step=flow.step,selection=selection,choices=table.concat(choices,"|"),created=state.test_created_agent}')
    s=s.replace('    return { open = false }','    return { open = false, created=state.test_created_agent }',1)
    s=s.replace('  command("create", {','  state.test_created_agent=agent\n  local function fixture_create(...) end\n  fixture_create("create", {',1)
    creation.write_text(s)
    pane=Path(installed['indicator']).with_name('92_account_switch.lua'); s=pane.read_text()
    rows=[['account','a','Work A','a@example.invalid','saved'],['account','b','Work B','b@example.invalid','saved'],
          ['indicator','fixture-source','Claude — Work A','Work A','running'],['inline','fixture-source','a','single','active','on']]
    fixture='\n'.join('\t'.join(quote(v,safe='') for v in row) for row in rows)
    value=dict(id='99999999-9999-4999-8999-999999999999',session='fixture-source',source_profile='a',target='b',proof_ready=True,approved=False,name='Project',
               accounts=[dict(name='a',label='Work A',email='a@example.invalid',orgId='Org A'),dict(name='b',label='Work B',email='b@example.invalid',orgId='Org B')])
    plan=receipt('simple-preview',value); value['proof_ready']=False; missing=receipt('simple-preview',value)
    s='local FIXTURE='+json.dumps(fixture)+'\nlocal PLAN='+json.dumps(plan)+'\nlocal MISSING='+json.dumps(missing)+'\n'+s
    s=s.replace('-- Conversation account strip', 'local run=function(key,cmd,opts) if key:match("^account%-switch%-") then state.test_command=cmd; state.test_answer=cmd:find("simple%-select") and (state.missing and MISSING or PLAN) or "Done" end end\n-- Conversation account strip',1)
    s=s.replace('local answer = (thurbox.runs or {})[key]','local answer = {state="done",ok=true,stdout=FIXTURE}')
    s=s.replace('local function result() return (thurbox.runs or {})[state.request_key or "none"] end','local function result() if state.request_key then return {state="done",ok=not state.test_error,stdout=state.test_answer or "Done",stderr=state.test_error and "Synthetic failure" or nil} end end')
    s=s.replace('  for _, row in ipairs(thurbox.sessions or {}) do if row.id == selected then session = row; break end end','  session={id=selected,agent="Claude — Work A"}')
    s=s.replace('  commands={','  commands={{action="account-switch.test-open",desc="Fixture"},{action="account-switch.test-missing",desc="Fixture"},{action="account-switch.test-change",desc="Fixture"},{action="account-switch.test-error",desc="Fixture"},')
    s=s.replace('dispatch=function(id)','''dispatch=function(id)
  if id=="account-switch.test-open" or id=="account-switch.test-missing" then
    store.selected="fixture-source"; state.test_error=nil; state.missing=id=="account-switch.test-missing"; return dispatch("account-switch.open")
  elseif id=="account-switch.test-change" then store.selected="different"; return true
  elseif id=="account-switch.test-error" then state.test_error=true; return true end''')
    s=s.replace('busy=busy(),operation=', 'test_command=state.test_command and state.test_command:sub(-230),busy=busy(),operation=')
    pane.write_text(s.replace("fixture-source",source_id).replace('store.selected="different"','store.selected="'+other_id+'"'))
    assert call('plugin','check')['ok']
    master,slave=pty.openpty()
    def resize(rows,cols=110):
        fcntl.ioctl(master,__import__('termios').TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
    resize(40)
    proc=subprocess.Popen([str(Path.home()/'.local/bin/thurbox')],stdin=slave,stdout=slave,stderr=slave,start_new_session=True); os.close(slave)
    output=bytearray()
    def drain():
        try:
            while True: output.extend(os.read(master,65536))
        except OSError: pass
    threading.Thread(target=drain,daemon=True).start()
    def state(): return call('ui','state')
    def projection(): return state()['plugin_state']['plugins/92_account_switch.lua']
    def action(name): call('ui','action',name); time.sleep(.2)
    def key(value): os.write(master,value); time.sleep(.2)
    try:
        for _ in range(60):
            try: state(); break
            except AssertionError: time.sleep(.1)
        key(b'\x0e')  # actual Ctrl+N
        assert state()['plugin_state']['plugins/70_new_session.lua']['open']
        key(b'\r')  # real denied-capability path must open Settings without recursion
        assert state()['modal'] is not None,state()
        key(b'\x1b'); key(b'\x1b')
        action('new_session.test-agent')
        choice=state()['plugin_state']['plugins/70_new_session.lua']['choices']
        assert 'Claude — Work A=Claude — Work A' in choice and 'codex=default' in choice and 'claude-accounts' not in choice,choice
        action('new_session.next'); action('new_session.next'); key(b'\r')
        assert state()['plugin_state']['plugins/70_new_session.lua']['created']=='Claude — Work A',state()
        action('account-switch.test-open'); key(b'\r')
        assert "'simple-select' '--session' '"+source_id+"' '--to' 'b'" in projection().get('test_command',''),state()
        assert projection()['plan'] and projection()['ready'],projection()
        before=projection()['test_command']
        resize(8,70); os.kill(proc.pid,signal.SIGWINCH); time.sleep(.3)
        action('account-switch.confirm'); assert projection()['test_command']==before and not projection()['ready'],projection()
        resize(40); os.kill(proc.pid,signal.SIGWINCH); time.sleep(.3)
        assert projection()['ready'],projection()
        action('account-switch.confirm'); assert "'simple-confirm'" in projection()['test_command'] and not projection()['open'],projection()
        action('account-switch.test-missing'); key(b'\r')
        action('account-switch.confirm'); assert "'simple-select'" in projection().get('test_command',''),state()
        key(b'\r')  # Review compatibility notice, no paid call yet
        assert "'verify-shared'" not in projection().get('test_command',''),state()
        action('account-switch.verify'); assert "'verify-shared' 'a' 'b'" in projection().get('test_command',''),state()
        action('account-switch.test-open'); key(b'\r'); action('account-switch.test-change')
        before=projection()['test_command']; action('account-switch.confirm'); assert projection()['test_command']==before,projection()
        key(b'\x1b'); action('account-switch.test-open'); key(b'\r'); action('account-switch.test-error')
        assert projection()['open']; key(b'\x1b'); assert not projection()['open']
        (root/'state.json').write_text(json.dumps(state(),indent=2)); (root/'terminal.bin').write_bytes(output)
        print(json.dumps(dict(ok=True,root=str(root),real_tui=True,ctrl_n_account_picker=True,inline_switch=True,small_screen_blocks_consent=True,paid_check_review=True,stale_selection_refused=True,no_auth_models_or_grants=True)))
    finally:
        (root/"terminal.bin").write_bytes(output)
        print("Fixture artifacts:",root)
        if proc.poll() is not None: print(bytes(output)[-3000:])
        if proc.poll() is None: os.killpg(proc.pid,signal.SIGTERM)
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
        os.close(master); subprocess.run([cli,'session','stop',source_id],capture_output=True,timeout=10); subprocess.run([cli,'session','stop',other_id],capture_output=True,timeout=10); subprocess.run([cli,'runtime','stop'],capture_output=True,timeout=10)

if __name__=='__main__': main()
