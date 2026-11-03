"""Render the login button in Thurbox's Lua VM with an intact synthetic URL."""
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


def main():
    root = Path(tempfile.mkdtemp(prefix='tbx-login-vm-', dir='/tmp'))
    env = dict(os.environ, THURBOX_CONFIG_DIR=str(root/'config'), THURBOX_DATA_DIR=str(root/'data'))
    cli = str(Path.home()/'.local/bin/thurbox-cli')
    subprocess.run([cli, 'plugin', 'new', 'accounts', '--json'], env=env, check=True, capture_output=True)
    with patch.dict(os.environ, env, clear=True):
        installed = install(cli, root/'accounts', '/fixture/claude')
    path = Path(installed['pane'])
    source = path.read_text()
    url = 'https://claude.ai/oauth/authorize?state=' + 'x'*500 + '&code_challenge=fixture'
    # Stub only the process/browser boundaries. Render and handlers are real Lua.
    source = ('local command=function(verb,opts) if verb=="open" then assert(opts.text==' + json.dumps(url) +
              ',"URL truncated"); state.opened=true end end\nlocal run=function() end\n' + source)
    source = source.replace('local answer = (thurbox.runs or {})[key]',
                            'local answer = {ok=true,stdout=' + json.dumps(url) + '}')
    source = source.replace('  render = function(ctx)', '  render = function(ctx)\n    state.login_profile="fixture"')
    source = source.replace('return {\n  name = "accounts"', 'local plugin = {\n  name = "accounts"')
    source += """
for _,width in ipairs({24,40,80}) do
  local node=plugin.render({width=width,height=24,focused=true})
  assert(state.login_url==""" + json.dumps(url) + """, "lost URL")
  plugin.on_click({id="open-login"})
  assert(state.opened,"browser action failed")
  state.opened=false
  plugin.on_action("accounts.open-login")
  assert(state.opened,"semantic browser action failed")
  state.opened=false
  plugin.on_key({key="tab"}); plugin.on_key({key="enter"})
  assert(state.opened,"keyboard browser action failed")
end
return plugin
"""
    path.write_text(source)
    result = subprocess.run([cli, 'plugin', 'check', '--json'], env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['ok'], result.stdout
    print(json.dumps(dict(ok=True, widths=[24,40,80], intact_url=True, click=True, keyboard=True, artifacts=str(root))))


if __name__ == '__main__':
    main()
