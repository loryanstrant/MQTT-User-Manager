'use strict';
const $ = (id) => document.getElementById(id);
let csrf = '', busy = false, editAction = 'add', selected = null, sort = 'username', direction = 'asc', queryVersion = 0;
const titles = {username: 'Account', note: 'What it’s for', status: 'Connection', last_seen: 'Last seen'};
const rotationWarning = 'Changing this password will not update the device. It may keep working until it reconnects, then it will be refused until you put the new password into it.';
function feedback(id, text) { $(id).textContent = text; $(id).hidden = !text; }
let generationVersion = 0;
function clearSecrets() { generationVersion++; $('account-password').value = ''; $('admin-password').value = ''; }
function showLogin() {
  clearSecrets(); $('edit-dialog').close(); $('remove-dialog').close();
  $('rows').replaceChildren(); $('accounts-panel').hidden = true; $('logout').hidden = true; $('login-panel').hidden = false;
}
async function api(url, method = 'GET', data = undefined) {
  let response;
  try {
    response = await fetch(url, {method, credentials: 'same-origin', cache: 'no-store', headers: {'Content-Type': 'application/json', ...(method !== 'GET' ? {'X-CSRF-Token': csrf} : {})}, ...(data !== undefined ? {body: JSON.stringify(data)} : {}), signal: AbortSignal.timeout(12000)});
  } catch (_) { throw new Error(method === 'GET' ? 'The page could not reach the manager. Refresh to check its state.' : 'The result is unknown. Do not resubmit; refresh the account list and check the recovery warning.'); }
  let result;
  try { result = await response.json(); } catch (_) { throw new Error('The manager returned an unreadable result. Check the account list before trying again.'); }
  if (!response.ok) {
    if (response.status === 401 && url !== '/auth/login') showLogin();
    throw new Error(result.message || 'The request could not be completed.');
  }
  return result;
}
function button(text, onClick, className = '') {
  const node = document.createElement('button'); node.type = 'button'; node.textContent = text; node.className = className; node.addEventListener('click', onClick); return node;
}
function cell(row, text, className) {
  const node = document.createElement('td'); node.textContent = text; node.className = className || ''; row.append(node); return node;
}
async function loadAccounts() {
  const version = ++queryVersion;
  try {
    const result = await api('/api/accounts?' + new URLSearchParams({q: $('search').value, status: $('status-filter').value, sort, direction}));
    if (version !== queryVersion) return;
    $('rows').replaceChildren(); $('total').textContent = `${result.total} accounts`; $('count').textContent = `${result.count} of ${result.total}`;
    $('file-state').textContent = result.critical ? '◐ Recovery required' : '● Account file readable';
    $('add').disabled = busy || result.critical;
    if (result.critical) feedback('page-feedback', '◐ Recovery required. Account changes are blocked. Follow the recovery guide before retrying.');
    for (const account of result.accounts) {
      const row = document.createElement('tr');
      const name = cell(row, account.username, 'account');
      if (account.protected) { const tag = document.createElement('span'); tag.className = 'protected'; tag.textContent = 'Protected from removal'; name.append(tag); }
      const note = cell(row, '', 'note'); note.append(button(account.note || 'Add a note', () => openEdit('note', account), 'subtle'));
      cell(row, account.status_label === '○ Disconnected' ? '○ Not connected' : account.status_label, 'state');
      const seen = cell(row, account.last_seen_local || 'Not seen in available logs', 'seen');
      if (account.presence_uncertain ?? account.log_incomplete) { const tag = document.createElement('span'); tag.className = 'protected'; tag.textContent = 'Incomplete log evidence'; seen.append(tag); }
      const actions = document.createElement('div'); actions.className = 'actions';
      const change = button('Change password', () => openEdit('change', account)); change.disabled = busy || result.critical;
      const remove = button(account.protected ? 'Protected' : 'Remove', () => openRemove(account), 'danger'); remove.disabled = busy || account.protected || result.critical;
      actions.append(change, remove); cell(row, '').append(actions); $('rows').append(row);
    }
    $('empty').hidden = result.count !== 0;
    $('empty').textContent = result.total ? 'No accounts match your search — Clear search.' : 'No accounts yet. Choose Add account to onboard a device.';
    for (const node of document.querySelectorAll('[data-sort]')) {
      const active = node.dataset.sort === sort;
      node.textContent = titles[node.dataset.sort] + (active ? (direction === 'asc' ? ' ▲ Ascending' : ' ▼ Descending') : ' ↕');
      node.parentElement.setAttribute('aria-sort', active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none');
    }
  } catch (error) {
    if (version !== queryVersion) return;
    $('rows').replaceChildren(); $('empty').hidden = true; $('count').textContent = ''; $('file-state').textContent = '○ Account list unavailable'; $('add').disabled = true;
    feedback('page-feedback', error.message);
  }
}
async function generated() {
  if (busy || !$('edit-dialog').open || editAction === 'note') return;
  const version = ++generationVersion;
  const current = () => version === generationVersion && !busy && $('edit-dialog').open && editAction !== 'note';
  try {
    const result = await api('/api/passwords/generate', 'POST', {});
    if (current()) $('account-password').value = result.password;
  } catch (error) { if (current()) feedback('edit-feedback', error.message); }
}
$('account-password').addEventListener('input', () => { generationVersion++; });
async function openEdit(action, account = null) {
  if (busy) return;
  selected = account; editAction = action; clearSecrets();
  $('edit-title').textContent = action === 'add' ? 'Add account' : action === 'change' ? `Change password: ${account.username}` : `Note: ${account.username}`;
  $('account-name').value = account ? account.username : ''; $('account-name').readOnly = action !== 'add';
  $('account-note').value = account ? account.note : ''; $('note-field').hidden = action === 'change';
  $('password-field').hidden = action === 'note'; $('account-password').required = action !== 'note';
  $('account-password').type = 'password'; $('show-password').textContent = 'Show';
  feedback('edit-warning', action === 'change' ? rotationWarning : ''); feedback('edit-feedback', '');
  $('edit-save').disabled = false; $('edit-cancel').disabled = false; $('generate').disabled = false;
  $('edit-save').textContent = action === 'add' ? 'Add account' : action === 'change' ? 'Change password' : 'Save note';
  $('edit-dialog').showModal();
  (action === 'add' ? $('account-name') : action === 'note' ? $('account-note') : $('account-password')).focus();
  if (action !== 'note') await generated();
}
function openRemove(account) {
  if (busy) return;
  selected = account; $('remove-title').textContent = `Remove account: ${account.username}`;
  feedback('remove-warning', `This account is ${account.status_label.toLowerCase()} according to available logs. Removing it prevents its next login. Existing connections may remain active. This cannot be undone without creating the account again with a new password.`);
  $('remove-name').value = ''; $('remove-save').disabled = true; $('remove-cancel').disabled = false; feedback('remove-feedback', '');
  $('remove-dialog').showModal(); $('remove-name').focus();
}
async function operation(data, id, dialog) {
  busy = true; generationVersion++; $('edit-save').disabled = true; $('remove-save').disabled = true; $('edit-cancel').disabled = true; $('remove-cancel').disabled = true; $('generate').disabled = true; $('logout').disabled = true;
  feedback(id, '◐ Checking the account change…');
  let resolved = false;
  try {
    const started = await api('/api/operations', 'POST', data);
    clearSecrets(); data.password = undefined;
    const until = Date.now() + 45000;
    while (Date.now() < until) {
      await new Promise(resolve => setTimeout(resolve, 500));
      const result = await api(started.poll_url);
      feedback(id, `${result.label}: ${result.message}`);
      if (result.status === 'running') continue;
      resolved = true;
      if (result.status !== 'succeeded') throw new Error(result.message);
      dialog.close(); feedback('page-feedback', `${result.label}: ${result.message}${result.warning ? ' ' + result.warning : ''}`); return;
    }
    throw new Error('The operation result is still unknown. Refresh the list and check the recovery warning; do not resubmit.');
  } catch (error) { feedback(id, '○ ' + error.message); }
  finally {
    data.password = undefined;
    busy = !resolved; clearSecrets(); $('edit-save').disabled = !resolved; $('edit-cancel').disabled = false; $('remove-cancel').disabled = false; $('logout').disabled = !resolved; $('generate').disabled = !resolved;
    $('remove-save').disabled = !resolved || $('remove-name').value !== selected?.username;
    if (!resolved) feedback('page-feedback', '◐ Outcome unknown. Further changes are blocked in this page. Refresh to inspect the accounts and recovery warning; do not repeat the change blindly.');
    await loadAccounts();
  }
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = event.submitter; submit.disabled = true; feedback('login-feedback', '◐ Signing in…');
  try {
    const result = await api('/auth/login', 'POST', {username: $('admin-name').value, password: $('admin-password').value}); csrf = result.csrf_token;
    clearSecrets(); $('login-panel').hidden = true; $('accounts-panel').hidden = false; $('logout').hidden = false; feedback('page-feedback', ''); await loadAccounts();
  } catch (error) { feedback('login-feedback', error.message); clearSecrets(); }
  finally { submit.disabled = false; }
});
$('logout').addEventListener('click', async () => { if (busy) return; try { await api('/auth/logout', 'POST', {}); showLogin(); csrf = (await api('/auth/csrf')).csrf_token; } catch (error) { feedback('page-feedback', error.message); } });
$('add').addEventListener('click', () => openEdit('add'));
$('generate').addEventListener('click', generated);
$('show-password').addEventListener('click', () => { const hidden = $('account-password').type === 'password'; $('account-password').type = hidden ? 'text' : 'password'; $('show-password').textContent = hidden ? 'Hide' : 'Show'; });
$('copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('account-password').value); feedback('edit-feedback', '● Password copied.'); } catch (_) { feedback('edit-feedback', 'Copy is unavailable here. Choose Show and copy the password manually.'); } });
$('edit-cancel').addEventListener('click', () => { if (!busy) { clearSecrets(); $('edit-dialog').close(); } });
$('remove-cancel').addEventListener('click', () => { if (!busy) $('remove-dialog').close(); });
for (const id of ['edit-dialog', 'remove-dialog']) $(id).addEventListener('cancel', event => { if (busy) event.preventDefault(); else clearSecrets(); });
$('edit-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  if (editAction === 'note') {
    $('edit-save').disabled = true;
    try { await api(`/api/accounts/${encodeURIComponent(selected.username)}/note`, 'PUT', {note: $('account-note').value}); $('edit-dialog').close(); feedback('page-feedback', '● Note saved.'); await loadAccounts(); }
    catch (error) { feedback('edit-feedback', error.message); }
    finally { $('edit-save').disabled = false; }
  } else await operation({action: editAction, username: $('account-name').value, password: $('account-password').value, ...(editAction === 'add' ? {note: $('account-note').value} : {})}, 'edit-feedback', $('edit-dialog'));
});
$('remove-name').addEventListener('input', () => { $('remove-save').disabled = busy || $('remove-name').value !== selected?.username; });
$('remove-form').addEventListener('submit', async event => { event.preventDefault(); if (!busy && $('remove-name').value === selected?.username) await operation({action: 'delete', username: selected.username}, 'remove-feedback', $('remove-dialog')); });
let debounce;
$('search').addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(loadAccounts, 250); });
$('status-filter').addEventListener('change', loadAccounts);
$('clear').addEventListener('click', () => { $('search').value = ''; $('status-filter').value = 'all'; loadAccounts(); });
for (const node of document.querySelectorAll('[data-sort]')) node.addEventListener('click', () => { direction = sort === node.dataset.sort && direction === 'asc' ? 'desc' : 'asc'; sort = node.dataset.sort; loadAccounts(); });
(async () => {
  try { csrf = (await api('/auth/csrf')).csrf_token; const session = await api('/auth/session'); csrf = session.csrf_token; $('login-panel').hidden = true; $('accounts-panel').hidden = false; $('logout').hidden = false; await loadAccounts(); }
  catch (_) { showLogin(); }
})();
setInterval(() => { if (!busy && !$('accounts-panel').hidden && !$('edit-dialog').open && !$('remove-dialog').open) loadAccounts(); }, 15000);
window.addEventListener('pagehide', clearSecrets);
