"""Reject credentials and private files in the publication tree and Git history."""
from pathlib import Path
import base64
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / '.git').is_dir() and (ROOT / 'github/.git').is_dir():
    ROOT = ROOT / 'github'
SECRET = re.compile(
    r'gsk_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|'
    r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|'
    r'(?<![A-Za-z0-9+/])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9+/])|(?<![A-Za-z0-9+/])AKIA[A-Z0-9]{16}(?![A-Za-z0-9+/])|'
    r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|'
    r'(?i:key|token|secret)[^\n]{0,80}[\"\x27][a-fA-F0-9]{32,64}[\"\x27]',
)
PRIVATE = re.compile(r'(^|/)(?:\.env(?:\..*)?|progress\.json|mistakes\.log|[^/]+\.(?:pem|key|p12|sqlite))$', re.IGNORECASE)
LOCAL_PATH = re.compile(r'[A-Z]:[\\/](?:Users|VM|NewOld)[\\/]', re.IGNORECASE)


def check_file(name, data):
    text = data.decode('utf-8', errors='ignore')
    if name.endswith('-b64.js'):
        text = re.sub(r'="([A-Za-z0-9+/=]+)"', lambda m: '=' + base64.b64decode(m[1], validate=True).decode('utf-8', errors='ignore'), text)
    reasons = []
    if PRIVATE.search(name):
        reasons.append('private filename')
    if SECRET.search(text):
        reasons.append('credential')
    if LOCAL_PATH.search(text):
        reasons.append('personal filesystem path')
    return [f'{name}: {reason}' for reason in reasons]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


if __name__ == '__main__':
    assert check_file('test.js', ('const key="' + 'gsk_' + 'A' * 48 + '"').encode())
    assert check_file('.env', b'')
    assert check_file('test.js', ('const token="' + 'a' * 40 + '"').encode())
    assert check_file('test.py', b'D:\\Users\\someone\\data')
    assert check_file('test-b64.js', b'const DATA="' + base64.b64encode(('gsk_' + 'A' * 48).encode()) + b'";')
    assert not check_file('test.js', b'const key="test-key-not-valid";')
    if (ROOT / '.git').is_dir():
        names = set(filter(None, git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0')))
    else:
        names = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not set(p.relative_to(ROOT).parts) & {'node_modules', '__pycache__', 'audit-artifacts', 'audit-fixtures'}}
    findings = []
    for name in sorted(names):
        path = ROOT / name
        if path.is_file():
            findings.extend(check_file(name, path.read_bytes()))
    commits = git('rev-list', '--all').decode().splitlines() if (ROOT / '.git').is_dir() else []
    for commit in commits:
        for name in filter(None, git('ls-tree', '-r', '--name-only', '-z', commit).decode().split('\0')):
            findings.extend(f'{commit[:8]}: {finding}' for finding in check_file(name, git('show', f'{commit}:{name}')))
    for finding in findings:
        print(finding)
    print(f'Publication scan: {len(names)} files, {len(commits)} commits, {len(findings)} findings')
    raise SystemExit(bool(findings))
