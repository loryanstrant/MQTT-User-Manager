'use strict';
// Executes the complete product script with a synthetic DOM and controlled requests.
// This is async behaviour coverage, not a substitute for browser layout verification.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('app/static/accounts.js', 'utf8');
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
async function rig() {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {value: '', textContent: '', hidden: false, disabled: false, open: false, listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; }, replaceChildren() {}, focus() {},
      close() { this.open = false; }, showModal() { this.open = true; }});
    return nodes.get(id);
  }
  const window = {listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }};
  const context = vm.createContext({document: {getElementById: node, querySelectorAll: () => []}, window,
    setInterval() {}, setTimeout, clearTimeout, URLSearchParams, AbortSignal,
    fetch: async () => ({ok: false, status: 401, json: async () => ({message: 'Synthetic signed out'})})});
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("loadAccounts = async () => {}; editAction = 'add';", context);
  node('edit-dialog').open = true;
  return {node, window, context, run: code => vm.runInContext(code, context)};
}
function generation(r, pending) {
  r.context.pending = pending;
  r.run('api = async () => pending.promise;');
  return r.run('generated()');
}
test('cancel, Escape and pagehide cannot restore cleared secrets', async () => {
  for (const dismiss of ['cancel', 'escape', 'pagehide']) {
    const r = await rig(), pending = deferred();
    const job = generation(r, pending);
    if (dismiss === 'cancel') r.node('edit-cancel').listeners.click();
    else if (dismiss === 'escape') { r.node('edit-dialog').listeners.cancel({preventDefault() {}}); r.node('edit-dialog').close(); }
    else r.window.listeners.pagehide();
    pending.resolve({password: 'synthetic-generated-password'}); await job;
    assert.equal(r.node('account-password').value, '');
  }
});
test('manual input wins over a pending generated password', async () => {
  const r = await rig(), pending = deferred(), job = generation(r, pending);
  r.node('account-password').value = 'synthetic-manual-password';
  r.node('account-password').listeners.input();
  pending.resolve({password: 'synthetic-generated-password'}); await job;
  assert.equal(r.node('account-password').value, 'synthetic-manual-password');
});
test('newest generation wins out-of-order requests', async () => {
  const r = await rig(), one = deferred(), two = deferred();
  const first = generation(r, one), second = generation(r, two);
  two.resolve({password: 'synthetic-newer-password'}); await second;
  one.resolve({password: 'synthetic-older-password'}); await first;
  assert.equal(r.node('account-password').value, 'synthetic-newer-password');
});
test('a reopened editor ignores old success and error responses', async () => {
  for (const failed of [false, true]) {
    const r = await rig(), pending = deferred(), job = generation(r, pending);
    r.node('edit-cancel').listeners.click();
    r.node('edit-dialog').open = true;
    r.node('account-password').value = 'synthetic-new-editor-password';
    r.node('edit-feedback').textContent = 'New editor feedback';
    if (failed) pending.reject(new Error('Old generation error'));
    else pending.resolve({password: 'synthetic-old-editor-password'});
    await job;
    assert.equal(r.node('account-password').value, 'synthetic-new-editor-password');
    assert.equal(r.node('edit-feedback').textContent, 'New editor feedback');
  }
});
test('uncertain operation clears payload secrets and invalidates pending generation', async () => {
  const r = await rig(), pending = deferred(), job = generation(r, pending);
  r.run("api = async () => { throw new Error('Synthetic network failure'); }; payload = {action:'add', username:'test', password:'synthetic-payload-password'};");
  await r.run("operation(payload, 'edit-feedback', $('edit-dialog'))");
  assert.equal(r.run('payload.password'), undefined);
  assert.equal(r.run('busy'), true);
  pending.resolve({password: 'synthetic-late-password'}); await job;
  assert.equal(r.node('account-password').value, '');
  assert.equal(r.node('edit-save').disabled, true);
});
test('note editor and closed editor cannot request generated passwords', async () => {
  const r = await rig();
  r.run('requests = 0; api = async () => { requests++; return {password:"synthetic"}; };');
  r.node('edit-dialog').open = false; await r.run('generated()');
  r.node('edit-dialog').open = true; r.run("editAction = 'note';"); await r.run('generated()');
  assert.equal(r.run('requests'), 0);
});
