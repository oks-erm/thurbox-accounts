"""Exercise name -> account selection with an upgraded older picker in the Lua VM."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thurbox_accounts.creation_ui import adapt


def main():
    cli=str(Path.home()/'.local/bin/thurbox-cli')
    original=Path(json.loads(subprocess.check_output([cli,'plugin','dir','--json']))['dir'])
    root=Path(tempfile.mkdtemp(prefix='tbx-new-vm-',dir='/tmp'))
    env=dict(os.environ,THURBOX_CONFIG_DIR=str(root/'config'),THURBOX_DATA_DIR=str(root/'data'))
    subprocess.run([cli,'plugin','new','accounts','--json'],env=env,check=True,capture_output=True)
    target=root/'config/ui/plugins/70_new_session.lua'
    # The installed picker is already owned/adapted, including the broken
    # reference left when an old installer replaces its helper block.
    source=adapt((original/'plugins/70_new_session.lua').read_text(),owned=True)
    source='''local state={}
local store={}
local thurbox={granted={sessions=true},agent_default="claude",agents={{name="claude"},{name="Claude — Work A"},{name="Claude — Work B"}},sessions={},commands={}}
local command=function() error("Session creation ran before account selection") end
'''+source
    source=source.replace('return {\n  name = "new_session"','local plugin = {\n  name = "new_session"')
    source+='''
for _,default in ipairs({"claude","Claude — Work B","codex"}) do
  thurbox.agent_default=default
  local flow=fresh(); flow.step="name"; flow.name=textinput.new("Test session")
  state.flow=flow
  assert(plugin.on_key({key="enter"}),"Enter declined")
  assert(state.flow.step=="agent","did not advance to account selection")
  local expected=default=="Claude — Work B" and 3 or default=="claude" and 2 or 1
  assert(state.flow.agent_index==expected,"wrong account preselected")
end
return plugin
'''
    target.write_text(source)
    result=subprocess.run([cli,'plugin','check','--json'],env=env,capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['ok'],result.stdout+result.stderr
    print(json.dumps(dict(ok=True,name_enter=True,named_default=True,artifacts=str(root))))

if __name__=='__main__': main()
