import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/mac-sign/skills/mac-sign/scripts/mac_sign.py'
spec = importlib.util.spec_from_file_location('mac_sign', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(root, name='Example', identifier='com.example.SignFixture'):
    app = root / (name + '.app')
    binary = app / 'Contents/MacOS' / name
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'placeholder')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': identifier, 'CFBundleExecutable': name,
        'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1'}))
    return app


class SelectionTests(unittest.TestCase):
    def test_preserves_existing_certificate_and_rejects_ambiguity(self):
        a = {'sha1': 'A' * 40, 'name': 'Apple Development: A'}
        b = {'sha1': 'B' * 40, 'name': 'Apple Development: B'}
        self.assertEqual(m.select_identity([a, b], previous=b['sha1']), b)
        for available, requested, previous in (([a, b], None, None), ([a], '-', None),
                                                ([a], None, b['sha1'])):
            with self.assertRaises(m.SignError):
                m.select_identity(available, requested, previous)

    def test_discovery_does_not_choose_newest_or_scan_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = fixture(root / 'dist')
            fixture(root / 'node_modules/vendor', 'Ignore')
            self.assertEqual(m.resolve_app(root, {}, None), a)
            fixture(root / 'other', 'Second')
            with self.assertRaises(m.SignError):
                m.resolve_app(root, {}, None)

    def test_config_rejects_shell_string_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for data in ({'build': 'echo hello'}, {'buid': ['./build.sh']}, {'app': 1}):
                (root / '.ai-sign.json').write_text(json.dumps(data))
                with self.assertRaises(m.SignError):
                    m.project_config(root)

    def test_output_cannot_replace_different_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = fixture(root)
            other = fixture(root, 'Other', 'com.example.Other')
            with patch.object(m, 'run') as run:
                with self.assertRaises(m.SignError):
                    m.sign_app(source, other, {'sha1': 'A' * 40})
                run.assert_not_called()
            self.assertEqual(m.app_info(other)['CFBundleIdentifier'], 'com.example.Other')

    def test_build_argv_does_not_expand_shell_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = '$(touch injected); `touch injected2`'
            m.build_project([sys.executable, '-c',
                             'import sys,pathlib;pathlib.Path("arg").write_text(sys.argv[1])',
                             value], root, 5)
            self.assertEqual((root / 'arg').read_text(), value)
            self.assertFalse((root / 'injected').exists())
            self.assertFalse((root / 'injected2').exists())


@unittest.skipUnless(sys.platform == 'darwin', 'uses real macOS codesign and clang')
class SigningIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        available = m.identities()
        try:
            cls.identity = m.select_identity(available)
        except m.SignError as exc:
            raise unittest.SkipTest(str(exc))
        cls.tmp = tempfile.TemporaryDirectory(prefix='mac-sign-tests-')
        cls.root = Path(cls.tmp.name)
        cls.binary = cls.root / 'fixture-binary'
        source = cls.root / 'fixture.c'
        source.write_text('int main(void) { return 0; }\n')
        subprocess.run(['/usr/bin/clang', str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.case.cleanup)
        self.path = Path(self.case.name)

    def app(self, name='Example'):
        app = fixture(self.path, name)
        binary = app / 'Contents/MacOS' / name
        binary.write_bytes(self.binary.read_bytes())
        binary.chmod(0o755)
        return app

    def test_sign_in_place_and_verify_requirement_after_rebuild(self):
        app = self.app()
        first = m.sign_app(app, app, self.identity)
        self.assertTrue(first['strict_verification'])
        plist = app / 'Contents/Info.plist'
        data = plistlib.loads(plist.read_bytes())
        data['CFBundleVersion'] = '2'
        plist.write_bytes(plistlib.dumps(data))
        second = m.sign_app(app, app, self.identity)
        self.assertTrue(second['previous_requirement_verified'])
        self.assertNotEqual(first['signature']['CDHash'], second['signature']['CDHash'])
        self.assertEqual(first['signature']['requirement'], second['signature']['requirement'])

    def test_fresh_unsigned_build_retains_installed_requirement(self):
        app = self.app()
        installed = self.path / 'Installed.app'
        first = m.sign_app(app, installed, self.identity)
        # The source remains linker-signed, as in a freshly rebuilt Swift product.
        second = m.sign_app(app, installed, self.identity)
        self.assertTrue(second['previous_requirement_verified'])
        self.assertEqual(first['signature']['requirement'], second['signature']['requirement'])

    def test_verification_failure_preserves_original(self):
        app = self.app()
        original = (app / 'Contents/MacOS/Example').read_bytes()
        with patch.object(m, 'verify', side_effect=m.SignError('injected verification failure')):
            with self.assertRaises(m.SignError):
                m.sign_app(app, app, self.identity)
        self.assertEqual((app / 'Contents/MacOS/Example').read_bytes(), original)
        self.assertEqual(list(self.path.glob('.mac-sign-*')), [])

    def test_nested_helper_and_entitlements_are_preserved(self):
        app = self.app()
        helper = app / 'Contents/Helpers/worker'
        helper.parent.mkdir()
        helper.write_bytes(self.binary.read_bytes())
        helper.chmod(0o755)
        entitlements = self.path / 'entitlements.plist'
        entitlement_data = {'com.apple.security.network.client': True}
        entitlements.write_bytes(plistlib.dumps(entitlement_data))
        m.run(['/usr/bin/codesign', '--force', '--sign', '-', '--options', 'runtime',
               '--entitlements', entitlements, app])
        result = m.sign_app(app, app, self.identity)
        self.assertEqual(result['signed_code_objects'], 2)
        self.assertEqual(m.leaf_hash(helper), self.identity['sha1'])
        extracted = m.run(['/usr/bin/codesign', '-d', '--entitlements', '-', '--xml', app])
        self.assertEqual(plistlib.loads(extracted.stdout.encode()), entitlement_data)
        details = m.run(['/usr/bin/codesign', '-d', '--verbose=4', app]).stderr
        self.assertIn('(runtime)', details)


if __name__ == '__main__':
    unittest.main()
