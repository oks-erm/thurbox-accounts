"""Exercise destination selection as scoped consent in the real Lua VM."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thurbox_accounts.accounts_ui import install


def main():
    root=Path(tempfile.mkdtemp(prefix='tbx-one-switch-',dir='/tmp'))
    env=dict(os.environ,THURBOX_CONFIG_DIR=str(root/'config'),THURBOX_DATA_DIR=str(root/'data'))
    cli=str(Path.home()/'.local/bin/thurbox-cli')
    subprocess.run([cli,'plugin','new','accounts','--json'],env=env,capture_output=True,check=True)
    with patch.dict(os.environ,env,clear=True): installed=install(cli,root/'accounts','/fixture/claude')
    path=Path(installed['pane']).with_name('92_account_switch.lua')
    source=path.read_text()
    prefix='''local state={}
local store={selected="source"}
local thurbox={runs={}}
local FIXTURE={label="Account: Work A",loaded=true,current="a",phase="active",mode="on",accounts={
{name="a",label="Work A",email="a@example.invalid",org="Org A",saved=true},
{name="b",label="Work B",email="b@example.invalid",org="Org B",saved=true}}}
'''
    prefix+='''local command=function(verb,opts) if verb=="focus" then assert(opts.text=="agent") end end
local run=function(key,cmd)
  assert(not cmd:find("verify%-shared"),"paid check invoked")
  assert(cmd:find("'%-%-consent'"),"destination click did not approve")
  if state.round==2 then
    assert(cmd:find("'%-%-session' 'replacement'"),"switch back used the original empty session")
    assert(cmd:find("'%-%-expected%-source' 'b'"),"wrong switch-back account")
  else
    assert(cmd:find("'%-%-expected%-source' 'a'"),"source not frozen")
    assert(cmd:find("'%-%-expected%-email' 'b@example.invalid'"),"target identity not frozen")
  end
  state.last_command=cmd
  thurbox.runs[key]={state="done",ok=true,stdout=state.round==2 and "switch-complete\\ta\\treplacement2" or "switch-complete\\tb\\treplacement"}
end
'''
    source=re.sub(r'local function model\(request\).*?\nlocal function summary',
                  'local function model(request) return FIXTURE end\nlocal function summary',source,count=1,flags=re.S)
    source=source.replace('return {\n  name="account-switch"','local plugin = {\n  name="account-switch"')
    source=prefix+source+'''
plugin.on_action("account-switch.open")
plugin.render({width=100,height=50})
assert(state.choice_ready,"selection notice did not fit")
FIXTURE.accounts[2].email="changed@example.invalid"
plugin.on_click({id="target:b"})
assert(state.last_command,"destination click did nothing")
store.selected="fallback-after-retirement"
plugin.render({width=100,height=50})
assert(not plugin.ui_state().open,"completed switch did not close")
assert(store.selected=="replacement","did not follow the new owner")
state.round=2; FIXTURE.current="b"; FIXTURE.label="Account: Work B"
plugin.on_action("account-switch.open")
assert(state.session=="replacement","reopened chooser is tied to stale source")
plugin.render({width=100,height=50})
plugin.on_click({id="target:a"})
plugin.render({width=100,height=50})
assert(store.selected=="replacement2","switch back did not follow the new owner")
return plugin
'''
    path.write_text(source)
    result=subprocess.run([cli,'plugin','check','--json'],env=env,capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['ok'],result.stdout+result.stderr
    print(json.dumps(dict(ok=True,one_click=True,no_paid_probe=True,identity_frozen=True,artifacts=str(root))))

if __name__=='__main__': main()
