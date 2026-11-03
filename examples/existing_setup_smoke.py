"""Check existing-session setup handoff in the real Lua VM without auth or sockets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thurbox_accounts.accounts_ui import install
from thurbox_accounts.pane import receipt


def main():
    root = Path(tempfile.mkdtemp(prefix='tbx-mode-vm-', dir='/tmp'))
    env = dict(os.environ, THURBOX_CONFIG_DIR=str(root/'config'), THURBOX_DATA_DIR=str(root/'data'))
    cli = str(Path.home()/'.local/bin/thurbox-cli')
    subprocess.run([cli, 'plugin', 'new', 'accounts', '--json'], env=env, check=True, capture_output=True)
    with patch.dict(os.environ, env, clear=True):
        installed = install(cli, root/'accounts', '/fixture/claude')
    path = Path(installed['pane'])
    data = ('account\ta\tWork A\ta@example.invalid\tsaved\n'
            'conversation\tmanaged\tProject (switchable)\ta\tshared\tb\t/project\trunning\tuuid\tactive\ton\towned\n'
            'current\tmanaged\nindicator\tmanaged\tclaude-accounts\tWork A\trunning')
    external = ('account\ta\tWork A\ta@example.invalid\tsaved\n'
                'conversation\toriginal\tOld project\t\tsingle\t\t/project\trunning\tuuid\tordinary\toff\texternal\n'
                'current\toriginal')
    named=data.replace('shared\tb\t/project','single\t\t/project')
    disabled=data.replace('active\ton\towned','active\toff\towned')
    success = receipt('mode-enable', dict(session='managed', profile='a'))
    source = '''local state={}
local store={selected="original"}
local thurbox={runs={},sessions={}}
local focused=0
local launched={}
local command=function(verb,opts) if verb=="focus" then assert(opts.text=="agent"); focused=focused+1 end end
local run=function(key,cmd) if key:match("^accounts%-operation") then launched[#launched+1]=cmd end; if key~="operation" and not state.pause_model then thurbox.runs[key]={state="done",ok=true,stdout=state.external_fixture or DATA} end end
'''.replace('DATA', json.dumps(data)) + 'local EXTERNAL=' + json.dumps(external) + '\n' + 'local NAMED=' + json.dumps(named) + '\nlocal DISABLED=' + json.dumps(disabled) + '\n' + path.read_text()
    source = source.replace('return {\n  name = "accounts"', 'local plugin = {\n  name = "accounts"')
    source += '''
local function ready(selected,ok,output)
  state={request_key="operation",setup_selected="original",screen="conversations"}
  store.selected=selected; focused=0
  thurbox.runs.operation={state="done",ok=ok,stdout=output,stderr="Setup refused"}
end
ready("original",true,SUCCESS)
plugin.render({width=100,height=40,focused=true})
assert(store.selected=="managed", "still showing the unverified original")
assert(state.conversation=="managed" and state.setup_profile=="a", "lost verified owner")
assert(focused==1,"did not focus the verified session")
plugin.render({width=100,height=40,focused=true})
assert(focused==1,"repeated render stole focus")
ready("other-work",true,SUCCESS)
plugin.render({width=100,height=40,focused=true})
assert(store.selected=="other-work" and focused==0,"stole focus from different work")
ready("original",false,"")
plugin.render({width=100,height=40,focused=true})
assert(store.selected=="original" and focused==0,"failed setup claimed success")
ready("original",true,"Compatibility check passed")
state.setup_after_check={request="operation",source="original",profiles={"a","b"}}
plugin.render({width=100,height=40,focused=true})
assert(#launched==1 and launched[1]:find("'mode%-preview' '%-%-session' 'original'"),"did not return to sharing review")
assert(not launched[1]:find("verify%-shared"),"silently repeated the paid check")
ready("original",false,"")
state.setup_after_check={request="operation",source="original",profiles={"a","b"}}
plugin.render({width=100,height=40,focused=true})
assert(#launched==1,"continued setup after failed compatibility check")
state={screen="sharing",external_fixture=EXTERNAL}; store.selected="original"
plugin.render({width=100,height=40,focused=true})
plugin.on_action("accounts.verify-account")
assert(launched[#launched]:find("'verify%-account' '%-%-session' 'original'"),"automatic account verification missing")
plugin.on_action("accounts.verify-as")
assert(launched[#launched]:find("'%-%-profile' 'a'"),"manual account verification missing")
state={screen="sharing",external_fixture=EXTERNAL}; store.selected="original"
plugin.render({width=100,height=40,focused=true})
local count=#launched
plugin.on_action("accounts.assign-account")
assert(state.pending.kind=="assign" and state.pending.profile=="a","assignment review missing")
assert(#launched==count,"assignment ran without consent")
plugin.render({width=100,height=40,focused=true})
plugin.on_action("accounts.confirm")
assert(launched[#launched]:find("'assign%-account'"),"assignment not submitted")
assert(launched[#launched]:find("'%-%-consent'"),"assignment consent missing")
local function contains(node,text)
  if type(node)=="string" then return node:find(text,1,true)~=nil end
  if type(node)~="table" then return false end
  for _,value in pairs(node) do if contains(value,text) then return true end end
  return false
end
ready("original",false,"")
state.pause_model=true
local waiting=plugin.render({width=100,height=40,focused=true})
assert(contains(waiting,"Setup refused"),"loading hid the operation failure")
state.pause_model=false
plugin.render({width=100,height=40,focused=true})
state.pause_model=true; state.request_number=20
local cached=plugin.render({width=100,height=40,focused=true})
assert(not contains(cached,"Loading your accounts"),"refresh discarded the loaded screen")
assert(contains(cached,"Setup refused"),"cached screen hid the operation failure")
store.selected="other-work"
local different=plugin.render({width=100,height=40,focused=true})
assert(contains(different,"Loading your accounts"),"reused stale data from a different selected session")
state={screen="conversations",external_fixture=NAMED}; store.selected="managed"
plugin.render({width=100,height=40,focused=true})
assert(plugin.ui_state().switching_mode=="on","guarded named session incorrectly reported Off")
state.conversation="original"; state.selection_base="managed"
plugin.on_action("accounts.conversations")
assert(state.conversation==nil,"Advanced conversations retained a stale row")
state={screen="conversations",external_fixture=DISABLED}; store.selected="managed"
plugin.render({width=100,height=40,focused=true})
assert(plugin.ui_state().switching_mode=="off","explicitly disabled shared session was silently enabled")
return plugin
'''.replace('SUCCESS', json.dumps(success))
    path.write_text(source)
    result = subprocess.run([cli, 'plugin', 'check', '--json'], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)['ok'], result.stdout + result.stderr
    print(json.dumps(dict(ok=True, owner_handoff=True, no_focus_theft=True, failure_preserved=True, artifacts=str(root))))


if __name__ == '__main__':
    main()
