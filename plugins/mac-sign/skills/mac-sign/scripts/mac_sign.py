#!/usr/bin/env python3
"""Local macOS development signing. Python standard library; no private-key access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import tempfile
import uuid

SKIP = {'.git', '.build', 'node_modules', 'Pods', '.venv', 'venv', '__pycache__'}
BUNDLES = {'.app', '.framework', '.xpc', '.appex', '.bundle'}
MACHO = {bytes.fromhex(x) for x in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
                                    'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


class SignError(Exception):
    pass


def run(argv, *, check=True, timeout=45, cwd=None):
    try:
        result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True,
                                text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SignError(f'{argv[0]} timed out after {timeout}s. Check for a pending '
                        'Keychain prompt; no access controls were changed.') from exc
    if check and result.returncode:
        raise SignError((result.stderr or result.stdout).strip() or
                        f'{argv[0]} exited {result.returncode}')
    return result


def identities():
    result = run(['/usr/bin/security', 'find-identity', '-v', '-p', 'codesigning'])
    return [{'sha1': sha, 'name': name} for sha, name in
            re.findall(r'\)\s+([A-Fa-f0-9]{40})\s+"([^"]+)"', result.stdout)]


def signature(app):
    result = run(['/usr/bin/codesign', '-d', '--verbose=4', app], check=False)
    if result.returncode:
        return None
    details = result.stderr + result.stdout
    req = run(['/usr/bin/codesign', '-d', '-r-', app])
    match = re.search(r'(?:# )?designated => (.+)', req.stdout + req.stderr)
    fields = dict(re.findall(r'^(Identifier|CDHash|TeamIdentifier)=(.+)$', details, re.M))
    fields['authorities'] = re.findall(r'^Authority=(.+)$', details, re.M)
    fields['requirement'] = match.group(1) if match else None
    return fields


def leaf_hash(app):
    with tempfile.TemporaryDirectory(prefix='mac-sign-cert-') as tmp:
        prefix = Path(tmp) / 'cert'
        run(['/usr/bin/codesign', '-d', '--extract-certificates=' + str(prefix), app])
        leaf = Path(str(prefix) + '0')
        return hashlib.sha1(leaf.read_bytes()).hexdigest().upper() if leaf.exists() else None


def select_identity(available, requested=None, previous=None):
    if requested:
        matches = [x for x in available if requested.upper() == x['sha1'].upper()
                   or requested == x['name']]
    elif previous:
        matches = [x for x in available if x['sha1'] == previous]
        if not matches:
            raise SignError('The App signing certificate is not available. Choose --identity '
                            'explicitly to change its signing identity.')
    else:
        matches = [x for x in available if x['name'].startswith('Apple Development:')]
    if len(matches) != 1:
        raise SignError('Expected one usable identity; run identities and select its exact '
                        'SHA-1 with --identity. Ad-hoc signing is not supported.')
    return matches[0]


def project_config(project):
    config_file = project / '.ai-sign.json'
    data = json.loads(config_file.read_text()) if config_file.exists() else {}
    if not isinstance(data, dict) or set(data) - {'app', 'output', 'identity', 'build', 'bundle_id'}:
        raise SignError('Invalid .ai-sign.json keys; use app, output, identity, build, bundle_id.')
    for key in ('app', 'output', 'identity', 'bundle_id'):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            raise SignError(f'.ai-sign.json {key} must be a nonempty string.')
    if 'build' in data and (not isinstance(data['build'], list) or not data['build'] or
                           any(not isinstance(x, str) or not x for x in data['build'])):
        raise SignError('.ai-sign.json build must be a nonempty argv array, not shell text.')
    return data


def project_path(value, project):
    path = Path(value).expanduser()
    return Path(os.path.abspath(path if path.is_absolute() else project / path))


def discover(project):
    candidates = []
    for root, dirs, _ in os.walk(project):
        root = Path(root)
        depth = len(root.relative_to(project).parts)
        kept = []
        for name in sorted(dirs):
            path = root / name
            if path.is_symlink() or name in SKIP or name.startswith('.'):
                continue
            if path.suffix == '.app':
                if (path / 'Contents/Info.plist').is_file():
                    candidates.append(path)
            elif depth < 5:
                kept.append(name)
        dirs[:] = kept
    return candidates


def app_info(app):
    if app.is_symlink() or not app.is_dir() or app.suffix != '.app':
        raise SignError(f'Expected an existing, non-symlink .app directory: {app}')
    plist = app / 'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    bundle_id = data.get('CFBundleIdentifier')
    executable = data.get('CFBundleExecutable')
    if not isinstance(bundle_id, str) or not bundle_id or not isinstance(executable, str):
        raise SignError(f'Missing CFBundleIdentifier/CFBundleExecutable: {plist}')
    binary = app / 'Contents/MacOS' / executable
    if not binary.is_file() or not binary.resolve().is_relative_to(app.resolve()):
        raise SignError(f'Invalid bundle executable: {binary}')
    return data


def resolve_app(project, config, explicit):
    value = explicit or config.get('app')
    if value:
        return project_path(value, project)
    candidates = discover(project)
    if len(candidates) != 1:
        raise SignError('Specify --app or .ai-sign.json app; candidates: ' +
                        json.dumps([str(x) for x in candidates], ensure_ascii=False))
    return candidates[0]


def code_targets(app):
    """Sign each real Mach-O or executable bundle once, from the inside out."""
    bundles, binaries, primary = {app}, set(), set()
    for root, dirs, files in os.walk(app, followlinks=False):
        root = Path(root)
        dirs[:] = [d for d in dirs if not (root / d).is_symlink()]
        if root.suffix in BUNDLES:
            for relative in ('Contents/Info.plist', 'Resources/Info.plist', 'Info.plist'):
                plist = root / relative
                if not plist.is_file():
                    continue
                executable = plistlib.loads(plist.read_bytes()).get('CFBundleExecutable')
                if not executable:
                    break
                for candidate in (root / 'Contents/MacOS' / executable, root / executable):
                    if candidate.is_file():
                        if not candidate.resolve().is_relative_to(app.resolve()):
                            raise SignError(f'Bundle executable escapes App: {candidate}')
                        bundles.add(root)
                        primary.add(candidate.resolve())
                        break
                break
        for name in files:
            path = root / name
            if path.is_symlink():
                continue
            with path.open('rb') as stream:
                if stream.read(4) in MACHO and 'Mach-O' in run(
                        ['/usr/bin/file', '--brief', path]).stdout:
                    binaries.add(path)
    return sorted(bundles | {p for p in binaries if p.resolve() not in primary},
                  key=lambda p: (-len(p.parts), str(p)))


def build_project(command, project, timeout):
    if not command:
        raise SignError('--build needs a reviewed build argv array in .ai-sign.json.')
    print('Building project…', file=sys.stderr, flush=True)
    with subprocess.Popen(command, cwd=project, stdout=sys.stderr, stderr=sys.stderr,
                          start_new_session=True) as proc:
        try:
            code = proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise SignError('Build interrupted or timed out; signing did not start.') from exc
    if code:
        raise SignError(f'Build exited {code}; signing did not start.')


def verify(app, requirement=None):
    args = ['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2']
    if requirement:
        args += ['-R', '=' + requirement]
    return run(args + [app])


def sign_app(source, destination, identity, expected_id=None):
    info = app_info(source)
    bundle_id = info['CFBundleIdentifier']
    if expected_id and bundle_id != expected_id:
        raise SignError(f'Bundle ID changed: expected {expected_id}, found {bundle_id}.')
    if destination.is_symlink() or destination.suffix != '.app':
        raise SignError('Output must be a non-symlink .app path.')
    src, dst = source.resolve(), destination.resolve()
    if src != dst and (dst.is_relative_to(src) or src.is_relative_to(dst)):
        raise SignError('Source and output may not contain each other.')
    if destination.exists() and app_info(destination)['CFBundleIdentifier'] != bundle_id:
        raise SignError('Output belongs to a different Bundle ID; choose another output.')
    source_signature = signature(source)
    source_leaf = leaf_hash(source) if source_signature and source_signature['authorities'] else None
    baseline = destination if destination.exists() else source
    before = signature(baseline)
    previous_leaf = leaf_hash(baseline) if before and before['authorities'] else None
    keep_requirement = previous_leaf == identity['sha1']
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mac-sign-', dir=destination.parent) as tmp:
        staged = Path(tmp) / source.name
        run(['/usr/bin/ditto', source, staged], timeout=180)
        targets = code_targets(staged)
        for target in targets:
            old = signature(target)
            metadata = 'identifier,entitlements,flags,runtime,launch-constraints,library-constraints'
            if target == staged and source_leaf == identity['sha1']:
                metadata += ',requirements'
            argv = ['/usr/bin/codesign', '--force', '--sign', identity['sha1'],
                    '--timestamp=none']
            if old:
                argv += ['--preserve-metadata=' + metadata]
            if target == staged:
                argv += ['--identifier', bundle_id]
            run(argv + [target])
        verify(staged, before['requirement'] if keep_requirement else None)
        after = signature(staged)
        if leaf_hash(staged) != identity['sha1'] or after['Identifier'] != bundle_id:
            raise SignError('Signed identity or Bundle ID does not match requested identity.')
        backup = destination.parent / ('.mac-sign-old-' + uuid.uuid4().hex + '.app')
        existed = destination.exists()
        if existed:
            destination.rename(backup)
        try:
            staged.rename(destination)
        except BaseException:
            if existed:
                backup.rename(destination)
            raise
        if existed:
            import shutil
            shutil.rmtree(backup)
    return {'status': 'signed', 'source': str(source), 'output': str(destination),
            'bundle_id': bundle_id, 'identity': identity, 'signed_code_objects': len(targets),
            'strict_verification': True, 'previous_signature': before,
            'previous_signature_path': str(baseline), 'signature': after,
            'previous_requirement_verified': bool(keep_requirement and before['requirement']),
            'privacy_permission_persistence': 'not tested', 'launched': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'identities', 'sign'])
    parser.add_argument('--project', default='.', help='Project root; defaults to current directory')
    parser.add_argument('--app', help='App path, relative to project or absolute')
    parser.add_argument('--output', help='Signed .app destination; defaults to source')
    parser.add_argument('--identity', help='Exact certificate SHA-1 or full name')
    parser.add_argument('--build', action='store_true', help='Run configured build before signing')
    parser.add_argument('--build-timeout', type=int, default=600)
    parser.add_argument('--report', help='Write verification JSON to this file')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SignError('This plugin requires a local macOS terminal.')
    if args.build and args.command != 'sign':
        raise SignError('--build is only supported with sign.')
    if args.build_timeout <= 0:
        raise SignError('--build-timeout must be positive.')
    available = identities()
    if args.command == 'identities':
        result = {'identities': available}
    else:
        project = Path(args.project).expanduser().resolve()
        if not project.is_dir():
            raise SignError(f'Project directory does not exist: {project}')
        config = project_config(project)
        if args.command == 'inspect':
            configured = args.app or config.get('app')
            apps = [project_path(configured, project)] if configured else discover(project)
            result = {'project': str(project), 'config': config, 'identities': available,
                      'apps': [{'path': str(app), 'exists': app.exists(),
                                'signature': signature(app) if app.exists() else None}
                               for app in apps]}
            output = args.output or config.get('output')
            if output:
                installed = project_path(output, project)
                result['output'] = {'path': str(installed), 'exists': installed.exists(),
                                    'signature': signature(installed) if installed.exists() else None}
        else:
            # Check key availability before spending time building.
            requested = args.identity or config.get('identity')
            source = resolve_app(project, config, args.app)
            output = args.output or config.get('output')
            destination = project_path(output, project) if output else source
            previous = destination if destination.exists() else source
            old = signature(previous) if previous.exists() else None
            old_leaf = leaf_hash(previous) if old and old['authorities'] else None
            identity = select_identity(available, requested, old_leaf)
            if args.report:
                report = Path(args.report).expanduser().resolve()
                if any(report.is_relative_to(p.resolve()) for p in (source, destination)):
                    raise SignError('Report must be outside the source and signed App.')
            if args.build:
                build_project(config.get('build'), project, args.build_timeout)
            result = sign_app(source, destination, identity, config.get('bundle_id'))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        report = Path(args.report).expanduser().absolute()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(payload)
    print(payload, end='')


if __name__ == '__main__':
    try:
        main()
    except (SignError, OSError, ValueError, plistlib.InvalidFileException) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
