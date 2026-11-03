import io
import os
import tempfile
import unittest
from pathlib import Path

from thurbox_accounts.login import login, link


class LoginTests(unittest.TestCase):
    def test_native_url_survives_chunk_boundaries_and_is_removed_on_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            url = 'https://claude.ai/oauth/authorize?state=' + 'a' * 400 + '&code_challenge=xyz'
            native = root / 'claude'
            native.write_text('#!/usr/bin/env python3\nimport sys,time\n'
                              f'sys.stdout.write("Open: {url[:200]}"); sys.stdout.flush()\n'
                              f'time.sleep(.05); print("{url[200:]}", flush=True)\n')
            native.chmod(0o700)
            seen = []

            class Output(io.StringIO):
                def write(self, text):
                    result = super().write(text)
                    value = link({'directory': str(root)})
                    if value:
                        seen.append(value)
                    return result

            output = Output()
            self.assertEqual(login(str(native), {'directory': str(root)}, os.environ.copy(), output), 0)
            self.assertIn(url, seen)
            self.assertIn(url, output.getvalue())
            self.assertEqual(link({'directory': str(root)}), '')

    def test_rejects_unrelated_urls_and_stale_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            native = root / 'claude'
            native.write_text('#!/bin/sh\nprintf "https://example.com/oauth/authorize?state=unrelated\\n"\nexit 7\n')
            native.chmod(0o700)
            self.assertEqual(login(str(native), {'directory': str(root)}, os.environ.copy(), io.StringIO()), 7)
            self.assertEqual(link({'directory': str(root)}), '')
