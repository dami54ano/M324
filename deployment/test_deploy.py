"""Exercise deploy.sh with real Linux file/symlink semantics and mocked services.

Run: python3 deployment/test_deploy.py
No sudo privileges, network connection or systemd installation required.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if sys.platform != 'linux':
    raise SystemExit('Run this regression test on Linux (also runs in CI).')

original = (Path(__file__).resolve().parents[1] / 'deploy.sh').read_text()
with tempfile.TemporaryDirectory(prefix='m324-deploy-test-') as directory:
    root = Path(directory)
    base = root / 'app'
    home = root / 'ubuntu'
    home.mkdir()
    binaries = root / 'bin'
    binaries.mkdir()
    commands = {
        'sudo': '#!/bin/bash\nif [[ "$1" == chown ]]; then exit 0; fi\nexec "$@"\n',
        'nginx': '#!/bin/bash\nexit 0\n',
        'systemctl': '#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_ROOT/service.log"\nexit 0\n',
        'sleep': '#!/bin/bash\nexit 0\n',
        'curl': '''#!/bin/bash
value=$(cat "$TEST_ROOT/app/current/build/version.txt")
[[ "$value" != "${FAIL_RELEASE:-}" ]] || exit 22
printf '%s' "$value"
''',
    }
    for name, contents in commands.items():
        command = binaries / name
        command.write_text(contents)
        command.chmod(0o755)
    script = root / 'deploy.sh'
    script.write_text(original.replace('/opt/ref-card', str(base))
                     .replace('/home/ubuntu', str(home))
                     .replace('/etc/systemd/system/ref-card.service', str(root / 'ref-card.service')))
    environment = dict(os.environ, PATH=str(binaries) + ':' + os.environ['PATH'], TEST_ROOT=str(root))

    def deploy(number, fail=False):
        release_id = 'a' * 40 + f'-42-{number}'
        source = root / f'source-{number}'
        (source / 'build').mkdir(parents=True)
        (source / 'deployment').mkdir()
        (source / 'build/index.html').write_text('<h1>OK</h1>')
        (source / 'build/version.txt').write_text(release_id + '\n')
        for name in ['nginx.conf', 'ref-card.service']:
            (source / 'deployment' / name).write_text('mock configuration\n')
        env = dict(environment, FAIL_RELEASE=release_id if fail else '')
        result = subprocess.run(['bash', str(script), str(source), release_id],
                                env=env, capture_output=True, text=True, timeout=30)
        expected = 1 if fail else 0
        assert result.returncode == expected, result.stdout + result.stderr
        return release_id

    deploy(1, fail=True)
    assert not os.path.lexists(base / 'current'), 'Failed first deployment left a current link'
    assert 'disable --now ref-card.service' in (root / 'service.log').read_text()
    print('PASS: failed first deployment stops service and removes current link')

    first = deploy(2)
    assert (base / 'current').resolve() == base / 'releases' / first
    print('PASS: initial successful deployment selects its release')

    deploy(3, fail=True)
    assert (base / 'current').resolve() == base / 'releases' / first
    assert (base / 'current/build/version.txt').read_text().strip() == first
    print('PASS: failed update restores previous release')

    latest = deploy(4)
    assert (base / 'current').resolve() == base / 'releases' / latest
    print('PASS: next successful deployment works after rollback')
