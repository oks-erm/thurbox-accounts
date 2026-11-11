import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from thurbox_accounts import processes


class ProcessStopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conversation = '33333333-3333-4333-8333-333333333333'
        self.settings = self.root / 'hooks-owner.json'

    def start(self, stubborn=False):
        worker = ('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'
                  if stubborn else 'import time; time.sleep(60)')
        script = ('import subprocess,sys,time; '
                  f'p=subprocess.Popen([sys.executable,"-c",{worker!r}]); '
                  f'open({str(self.root / "child")!r},"w").write(str(p.pid)); time.sleep(60)')
        child = subprocess.Popen([sys.executable, '-c', script, '--resume', self.conversation,
                                  '--settings', str(self.settings)])
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.wait()
            path = self.root / 'child'
            if path.exists():
                try:
                    os.kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 3
        while not (self.root / 'child').exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue((self.root / 'child').exists())
        time.sleep(.05)  # Worker installs its TERM handler before the test signals it.
        return child, int((self.root / 'child').read_text())

    def test_stop_includes_background_descendant(self):
        parent, worker = self.start()
        evidence = processes.stop_tree(parent.pid, sys.executable, self.conversation, self.settings)
        parent.wait(timeout=2)
        self.assertIsNotNone(parent.returncode)
        self.assertTrue({parent.pid, worker}.issubset({p['pid'] for p in evidence['processes']}))
        self.assertEqual(set(evidence['forced']), {parent.pid, worker})
        self.assertFalse(processes.alive(evidence['processes']))

    def test_stubborn_worker_is_killed_and_verified(self):
        parent, worker = self.start(stubborn=True)
        evidence = processes.stop_tree(parent.pid, sys.executable, self.conversation, self.settings)
        parent.wait(timeout=2)
        self.assertIn(worker, evidence['forced'])
        self.assertFalse(processes.alive(evidence['processes']))

    def test_different_conversation_or_settings_never_signals_process(self):
        parent, _ = self.start()
        for conversation, settings in [('wrong', self.settings), (self.conversation, self.root / 'other.json')]:
            with self.assertRaisesRegex(ValueError, 'identity'):
                processes.stop_tree(parent.pid, sys.executable, conversation, settings)
            self.assertIsNone(parent.poll())

    def test_missing_native_pid_is_not_shutdown_proof(self):
        with self.assertRaisesRegex(ValueError, 'verify'):
            processes.stop_tree(99999999, sys.executable, self.conversation, self.settings)

    def test_reused_pid_is_not_a_signal_target(self):
        old = dict(pid=123, uid=os.getuid(), start='old', status='S')
        reused = dict(old, start='new')
        with patch.object(processes, 'snapshot', return_value={123: reused}), patch.object(os, 'kill') as kill:
            self.assertFalse(processes.alive([old]))
            processes._signal(old, signal.SIGKILL)
        kill.assert_not_called()

    def test_captured_tree_is_durable_before_parent_shutdown(self):
        parent, worker = self.start()
        captured = []
        def prepared(evidence):
            self.assertIsNone(parent.poll())
            self.assertTrue({parent.pid, worker}.issubset({p['pid'] for p in evidence['processes']}))
            captured.append(evidence)
        processes.stop_tree(parent.pid, sys.executable, self.conversation, self.settings, prepared=prepared)
        self.assertTrue(captured)

    def test_exit_handler_cannot_spawn_an_untracked_detached_worker(self):
        marker = self.root / 'untracked'
        ready = self.root / 'ready'
        script = ('import os,signal,subprocess,sys,time\n'
                  'def handler(*args):\n'
                  ' p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],start_new_session=True)\n'
                  f' open({str(marker)!r},"w").write(str(p.pid))\n'
                  ' os._exit(0)\n'
                  'signal.signal(signal.SIGTERM,handler)\n'
                  f'open({str(ready)!r},"w").close()\n'
                  'time.sleep(60)\n')
        parent = subprocess.Popen([sys.executable,'-c',script,'--resume',self.conversation,'--settings',str(self.settings)])
        self.addCleanup(lambda: parent.poll() is None and parent.kill())
        self.addCleanup(lambda: marker.exists() and os.kill(int(marker.read_text()),signal.SIGKILL))
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(ready.exists())
        processes.stop_tree(parent.pid,sys.executable,self.conversation,self.settings)
        parent.wait(timeout=2)
        self.assertFalse(marker.exists(), 'Exit handler spawned a worker outside the captured tree')

    def test_missing_root_before_freeze_is_not_vacuous_shutdown_proof(self):
        root = dict(pid=123,uid=os.getuid(),start='one',status='S',parent=1)
        args = [sys.executable,'--resume',self.conversation,'--settings',str(self.settings)]
        with patch.object(processes,'snapshot',side_effect=[{123:root},{123:root},{}]), \
                patch.object(processes,'_argv',return_value=args), \
                patch.object(processes,'_signal'), patch.object(processes,'alive',return_value={}), \
                self.assertRaisesRegex(ValueError,'exited before'):
            processes.stop_tree(123,sys.executable,self.conversation,self.settings)

    def test_pinned_native_identity_accepts_replaced_title(self):
        parent, _ = self.start()
        identity = processes.snapshot()[parent.pid]
        identity.update(command=str(Path(sys.executable).resolve()),conversation=self.conversation,settings=str(self.settings))
        # A title or flattened macOS path with an apostrophe need not parse.
        with patch.object(processes,'_argv',side_effect=ValueError('unparseable title')):
            evidence = processes.stop_tree(parent.pid,sys.executable,self.conversation,self.settings,identity=identity)
        parent.wait(timeout=2)
        self.assertFalse(processes.alive(evidence['processes']))

    def test_pinned_launch_accepts_shebang_and_exec_wrapper(self):
        for name, code in [('shebang',f'#!{sys.executable}\nimport time\ntime.sleep(60)\n'),
                           ('wrapper',f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c '
                            '\'import time;time.sleep(60)\' "$@"\n')]:
            with self.subTest(name=name):
                native = self.root / name
                native.write_text(code)
                native.chmod(0o700)
                child = subprocess.Popen([str(native),'--resume',self.conversation,'--settings',str(self.settings)])
                try:
                    identity = processes.snapshot()[child.pid]
                    identity.update(command=str(native.resolve()),conversation=self.conversation,settings=str(self.settings))
                    evidence = processes.stop_tree(child.pid,str(native),self.conversation,self.settings,identity=identity)
                    self.assertFalse(processes.alive(evidence['processes']))
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.wait()

    def test_worker_exit_before_freeze_cannot_hide_detached_descendants(self):
        root = dict(pid=123,uid=os.getuid(),start='one',status='S',parent=1)
        child = dict(root,pid=124,start='two',parent=123)
        initial = {123:root,124:child}
        frozen_root = {123:dict(root,status='T')}
        args = [sys.executable,'--resume',self.conversation,'--settings',str(self.settings)]
        with patch.object(processes,'snapshot',side_effect=[initial,initial,frozen_root]), \
                patch.object(processes,'_argv',return_value=args), patch.object(processes,'_signal'), \
                self.assertRaisesRegex(ValueError,'worker exited before'):
            processes.stop_tree(123,sys.executable,self.conversation,self.settings)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux old-supervisor lease inspection')
    def test_old_supervisor_lease_verifies_native_after_title_replaces_argv(self):
        folder = self.root / 'Account Store'
        folder.mkdir()
        launcher = folder / 'thurbox-accounts-agent'
        lease = folder / ('writer-' + self.conversation + '.lock')
        pidfile = folder / 'native-pid'
        launcher.write_text('import fcntl,os,subprocess,sys\n'
            f'fd=os.open({str(lease)!r},os.O_CREAT|os.O_RDWR,0o600)\n'
            'fcntl.flock(fd,fcntl.LOCK_EX)\n'
            'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\n'
            f'open({str(pidfile)!r},"w").write(str(p.pid))\n'
            'p.wait()\n')
        supervisor = subprocess.Popen([sys.executable,str(launcher),'--resume',self.conversation])
        def cleanup():
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()),signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if supervisor.poll() is None:
                supervisor.kill()
            supervisor.wait()
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 3
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(pidfile.exists())
        native_pid = int(pidfile.read_text())
        argv = processes._argv
        def titled(pid):
            return ['claude'] if pid == native_pid else argv(pid)
        with patch.object(processes,'_argv',side_effect=titled):
            missing_lease = folder / 'other.lock'
            missing_lease.touch()
            with self.assertRaisesRegex(ValueError,'identity'):
                processes.stop_tree(native_pid,sys.executable,self.conversation,self.settings,
                                    launcher=launcher,writer=missing_lease)
            evidence = processes.stop_tree(native_pid,sys.executable,self.conversation,self.settings,
                                           launcher=launcher,writer=lease)
        supervisor.wait(timeout=2)
        self.assertFalse(processes.alive(evidence['processes']))

