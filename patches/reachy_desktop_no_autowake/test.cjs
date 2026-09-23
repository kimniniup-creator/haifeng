// Offline execution of the actual patched TSX; all external effects are trapped.
// Usage: node test.cjs <offline-checkout> <typescript-module-path>
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const crypto = require('node:crypto');
const ts = require(path.resolve(process.argv[3]));
const root = path.resolve(process.argv[2]);
const spec = require('./manifest.json');
const source = fs.readFileSync(path.join(root, spec.path), 'utf8').replace(/\r\n/g, '\n');
assert.equal(crypto.createHash('sha256').update(source).digest('hex'), spec.patched_sha256_lf);
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
}, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);

function harness(mode, failingUrl = null) {
  let values = [], refs = [], cursor = 0, refCursor = 0;
  const requests = [], transitions = [], sockets = [];
  let currentMode = mode;
  const state = { transitionTo: { ready: () => transitions.push('ready') }, setHardwareError() {} };
  const store = () => state;
  store.getState = () => ({ robotStateFull: { data: { control_mode: currentMode } } });
  const react = {
    useCallback: fn => fn,
    useState: initial => { const i = cursor++; if (!(i in values)) values[i] = initial; return [values[i], value => { values[i] = value; }]; },
    useRef: initial => { const i = refCursor++; return refs[i] ||= { current: initial }; },
  };
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx },
    '@mui/material': { Box: 'Box', Alert: 'Alert', Button: 'Button' },
    './StartupView': { default: 'StartupView' },
    '../../store/useAppStore': { default: store },
    '@styles': { BLUR: { lg: '' }, useAppPalette: () => ({ surfaceCard: '#fff' }) },
    '../../config/daemon': {
      DAEMON_CONFIG: { TIMEOUTS: { COMMAND: 1 } }, buildApiUrl: p => p, getWsBaseUrl: () => 'blocked:',
      fetchWithTimeout: async (url, options) => { requests.push({ url, ...options }); return { ok: url !== failingUrl, json: async () => ({}) }; },
    },
  };
  const exports = {};
  vm.runInNewContext(compiled.outputText, {
    exports, require: name => { assert.ok(name in modules, `Unexpected import ${name}`); return modules[name]; },
    setTimeout: fn => { queueMicrotask(fn); return 1; }, clearTimeout() {},
    WebSocket: class { constructor(url) { sockets.push(url); throw Error('Unexpected socket'); } },
    fetch: () => { throw Error('Unexpected global fetch'); }, console,
  });
  const render = () => { cursor = refCursor = 0; return exports.default({}); };
  function find(node, type) {
    if (!node || typeof node !== 'object') return;
    if (node.type === type) return node;
    for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, type); if (found) return found; }
  }
  return { requests, transitions, sockets, render, find, setMode: value => { currentMode = value; } };
}

for (const scenario of ['first connection', 'reconnect', 'webview recovery', 'repeated completion']) {
  for (const mode of ['disabled', 'enabled', undefined, 'gravity_compensation']) {
    test(`${scenario}, ${mode}: completion never writes or enters active controls`, async () => {
      const h = harness(mode);
      const callback = h.find(h.render(), 'StartupView').props.onScanComplete;
      await callback(); await callback();
      assert.deepEqual(h.requests, []); assert.deepEqual(h.sockets, []); assert.deepEqual(h.transitions, []);
      assert.ok(h.find(h.render(), 'Button'));
    });
  }
}
test('explicit disabled wake click sends exactly enable then wake, double click is ignored', async () => {
  const h = harness('disabled');
  h.find(h.render(), 'StartupView').props.onScanComplete();
  const click = h.find(h.render(), 'Button').props.onClick;
  await Promise.all([click(), click()]);
  assert.deepEqual(h.requests.map(r => r.url), ['/api/motors/set_mode/enabled', '/api/move/play/wake_up']);
  assert.ok(h.requests.every(r => r.method === 'POST'));
  assert.deepEqual(h.transitions, ['ready']);
});
test('explicit already-enabled click opens controls without sending an action', async () => {
  const h = harness('enabled'); h.find(h.render(), 'StartupView').props.onScanComplete();
  await h.find(h.render(), 'Button').props.onClick();
  assert.deepEqual(h.requests, []); assert.deepEqual(h.transitions, ['ready']);
});
test('click reads current mode, unknown mode fails closed', async () => {
  const h = harness('disabled'); h.find(h.render(), 'StartupView').props.onScanComplete(); h.setMode(undefined);
  await h.find(h.render(), 'Button').props.onClick();
  assert.deepEqual(h.requests, []); assert.deepEqual(h.transitions, []);
});
for (const failure of ['/api/motors/set_mode/enabled', '/api/move/play/wake_up']) {
  test(`HTTP failure ${failure} does not enter active controls or retry`, async () => {
    const h = harness('disabled', failure); h.find(h.render(), 'StartupView').props.onScanComplete();
    await h.find(h.render(), 'Button').props.onClick();
    assert.deepEqual(h.transitions, []); assert.equal(h.requests.length, failure.includes('set_mode') ? 1 : 2);
  });
}
