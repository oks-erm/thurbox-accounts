"""Build a dependency-free native Mac companion, replacing only owned bundles."""
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import sys
import tempfile
import time

from .core import atomic_write
from .runtime import execute

OWNER = 'thurbox-accounts-desktop-v1'

def install(app_dir, accounts_dir, claude, thurbox):
    app_dir = app_dir.expanduser().absolute()
    app = app_dir/'Thurbox Accounts.app'
    marker = app/'Contents/Resources/owner.txt'
    if app.is_symlink() or (app.exists() and (any(parent.is_symlink() for parent in [app/'Contents',app/'Contents/Resources']) or app.stat().st_uid != os.getuid() or not marker.is_file() or marker.is_symlink() or marker.read_text().strip() != OWNER)):
        raise ValueError('Refusing to replace an unrelated app bundle; choose another --app-dir')
    if platform.system() != 'Darwin':
        raise ValueError('The desktop companion currently requires macOS 13 or newer')
    source = Path(__file__).resolve().parents[1]
    swift = source/'desktop/Accounts.swift'
    if not swift.is_file():
        raise ValueError('Desktop source is missing; install the latest extension checkout first')
    native, backend = shutil.which(claude), shutil.which(thurbox)
    if not native or not backend:
        raise ValueError('Claude and Thurbox CLI must be installed before desktop-install')
    app_dir.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.thurbox-accounts-build-',dir=app_dir))
    bundle = staging/app.name
    binary = bundle/'Contents/MacOS/ThurboxAccounts'
    resources = bundle/'Contents/Resources'
    binary.parent.mkdir(parents=True)
    resources.mkdir(parents=True)
    architecture = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
    command = ['xcrun','swiftc','-swift-version','5','-parse-as-library',str(swift),'-o',str(binary),
               '-target',architecture+'-apple-macosx13.0','-framework','SwiftUI','-framework','AppKit',
               '-module-cache-path',str(Path(tempfile.gettempdir())/'thurbox-accounts-swift-cache')]
    compiled = execute(command,source,timeout=240,limit=262144)
    if compiled['status'] != 'PASS' or compiled['truncated']:
        raise ValueError('Desktop build failed. Install Apple Command Line Tools with xcode-select --install. ' + compiled.get('stderr','')[-3000:])
    config = dict(argv=[sys.executable,str(source/'bin/thurbox-accounts'),
        '--accounts-dir',str(accounts_dir.expanduser().absolute()),'--claude',str(Path(native).absolute()),
        '--thurbox-cli',str(Path(backend).absolute())])
    atomic_write(resources/'backend.json',json.dumps(config,indent=2)+'\n')
    atomic_write(resources/'owner.txt',OWNER+'\n')
    info = dict(CFBundleIdentifier='dev.thurbox.accounts',CFBundleName='Thurbox Accounts',
        CFBundleExecutable='ThurboxAccounts',CFBundlePackageType='APPL',CFBundleShortVersionString='0.3.0',
        CFBundleVersion='3',LSMinimumSystemVersion='13.0',NSHighResolutionCapable=True)
    (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    signed = execute(['/usr/bin/codesign','--force','--sign','-',str(bundle)],source,timeout=30,limit=65536)
    if signed['status'] != 'PASS':
        raise ValueError('Local app signing failed: ' + signed.get('stderr','')[-1000:])
    backup = None
    if app.exists():
        # Recheck ownership immediately before the only replacement operation.
        if marker.is_symlink() or marker.read_text().strip() != OWNER:
            raise ValueError('App ownership changed during build; preserved')
        backup = app.with_name(app.name+'.backup.'+str(time.time_ns()))
        os.rename(app,backup)
    try:
        os.rename(bundle,app)
    except OSError:
        if backup and not app.exists():
            os.rename(backup,app)
        raise
    return dict(app=str(app),backup=str(backup) if backup else None,
        next='Open Thurbox Accounts.app. Add/login accounts, create a conversation and enable sharing once.')
