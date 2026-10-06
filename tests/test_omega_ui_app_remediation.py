"""Run the App remediation checks with the existing frontend toolchain."""
import hashlib
import json
import re
import shutil
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[1]
NPM = shutil.which("npm.cmd") or shutil.which("npm")


def run_frontend(*args):
    assert NPM, "npm is required for UI verification"
    result = subprocess.run(
        [NPM, "--prefix", "omega-ui", *args], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def test_shortcuts_accessibility_and_listener_cleanup():
    run_frontend("run", "test", "--", "src/test/app_remediation.test.tsx")


def test_production_build():
    run_frontend("run", "build")


def test_missing_integrations_fail_closed():
    run_frontend("run", "test", "--", "src/test/missing_integrations.test.tsx")


def test_full_frontend_suite():
    run_frontend("run", "test")


def test_verification_runner_rejects_failed_commands(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "injected failure", ""))
    with pytest.raises(AssertionError, match="injected failure"):
        run_frontend("run", "build")


def test_verification_runner_rejects_missing_npm(monkeypatch):
    monkeypatch.setattr(__name__ + ".NPM", None)
    with pytest.raises(AssertionError, match="npm is required"):
        run_frontend("run", "build")


def test_llm_config_fixture_restores_nested_snapshot_after_failure():
    from copy import deepcopy
    from tests import test_ui_llm_config, test_ui_copilot_direct_llm
    from omega.api.routes import copilot

    config = copilot._IN_MEMORY_LLM_CONFIG
    snapshot = deepcopy(config)
    for module in (test_ui_llm_config, test_ui_copilot_direct_llm):
        fixture = module.restore_llm_config.__wrapped__()
        next(fixture)
        try:
            with pytest.raises(RuntimeError, match="injected failure"):
                config["global_profile"]["model"] = "injected mutation"
                config["injected_profile"] = {"model": "injected"}
                raise RuntimeError("injected failure")
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass
        assert copilot._IN_MEMORY_LLM_CONFIG is config
        assert config == snapshot


def test_verification_runner_propagates_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("npm", 120)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        run_frontend("run", "test")


def test_rem7_repo_sources_and_artifacts_fail_closed():
    session = 'l4_role13_omega_ui_ux_promax_redesign_rem7_20261004'
    for name, expected in [
        ('anti_drip_contract', '5c53326e2b8e51a330e2ec2e31a3ab6540ba253472dab13cd46509a235e4749d'),
        ('graph_evidence', 'd8ef55c82b66d728c7fca649725b381096bc347cc302320907d10ad419ac82df'),
    ]:
        raw = (ROOT / f'.ly_state/session/{name}_{session}.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        assert hashlib.sha256(raw + b' ').hexdigest() != expected
        with pytest.raises(FileNotFoundError):
            (ROOT / f'.ly_state/session/missing_{name}_{session}.json').read_bytes()
    role = ROOT / '.agents/agent/ui-ux-integrator.md'
    declared = role.read_text(encoding='utf-8').split('skills:\n', 1)[1].split('sod_boundary:', 1)[0]
    skills = re.findall(r'^- ([\w-]+)$', declared, re.MULTILINE)
    assert len(skills) == 10
    for skill in skills:
        source = ROOT / '.agents/skills' / skill / 'skill.md'
        assert source.read_text(encoding='utf-8').startswith('---')
    graph = json.loads((ROOT / f'.ly_state/session/graph_evidence_{session}.json').read_bytes())
    result = subprocess.run(['git', 'ls-files', '--', *graph['scope_files']], cwd=ROOT,
                            capture_output=True, text=True, timeout=30, check=True)
    assert set(graph['scope_files']) <= set(result.stdout.splitlines())
    result = subprocess.run([
        shutil.which('node'), str(ROOT / 'omega-ui/node_modules/vitest/vitest.mjs'),
        'list', '--config', 'omega-ui/vite.config.ts', '--filesOnly', '--json',
    ], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90, check=True)
    discovered = {Path(item['file']).name for item in json.loads(result.stdout)}
    for name in ('app_remediation.test.tsx', 'missing_integrations.test.tsx'):
        assert name in discovered
        assert f'omega-ui/src/test/{name}' in graph['scope_files']
        source = f'omega-ui/src/test/{name}'
        raw = (ROOT / source).read_bytes()
        assert raw
        indexed = subprocess.run(['git', 'show', f':{source}'], cwd=ROOT,
                                 capture_output=True, timeout=30, check=True).stdout
        assert indexed.replace(b'\r\n', b'\n') == raw.replace(b'\r\n', b'\n')


@pytest.mark.parametrize('locale', ['en', 'vi'])
def test_rem7_native_unavailable_dialog_keyboard_lifecycle(locale):
    from playwright.sync_api import sync_playwright, expect

    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'omega-ui/dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/**', lambda route: route.abort())
                page.add_init_script(f"localStorage.setItem('omega_quant_locale', '{locale}')")
                page.goto(f'http://127.0.0.1:{server.server_port}')
                for name in (['Copilot', 'Configuration', 'OPS (0)'] if locale == 'en'
                             else ['Copilot', 'Cấu hình', 'TÁC VỤ (0)']):
                    launcher = page.locator('header').get_by_role('button', name=name, exact=True)
                    launcher.click()
                    dialog = page.get_by_role('dialog')
                    expect(dialog).to_be_visible()
                    if name in ('Copilot', 'Configuration', 'Cấu hình'):
                        expect(dialog.get_by_role('alert')).to_have_text(
                            'This integration is unavailable in this build.' if locale == 'en'
                            else 'Tích hợp này không khả dụng trong bản dựng này.')
                    assert dialog.evaluate('(d) => d.contains(document.activeElement)')
                    for key in ('Tab', 'Shift+Tab', 'Tab', 'Tab', 'Shift+Tab'):
                        page.keyboard.press(key)
                        assert dialog.evaluate('(d) => d.contains(document.activeElement) || document.activeElement === document.body')
                        assert not launcher.evaluate('(b) => b === document.activeElement')
                    page.keyboard.press('Escape')
                    expect(dialog).to_have_count(0)
                    expect(launcher).to_be_focused()
                    launcher.click()
                    dialog.get_by_role('button').first.click()
                    expect(page.get_by_role('dialog')).to_have_count(0)
                    expect(launcher).to_be_focused()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
