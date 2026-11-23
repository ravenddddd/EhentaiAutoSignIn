'use strict';

const $ = (id) => document.getElementById(id);

const RESULT_LABELS = {
  success: 'Signed in',
  already: 'Already signed in',
  encounter: 'Random Encounter',
  unconfigured: 'Not configured',
  unknown: 'Unknown',
  error: 'Error',
};

const SOURCE_LABELS = {
  'exchange.php?t=gp': 'GP Exchange',
  'exchange.php?t=hath': 'Hath Exchange',
  'hathperks.php': 'Hath Perks',
};

let pollTimer = null;

async function api(path, options) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...(options || {}),
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'ehentai-signin',
    },
  });
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }
  if (!response.ok) {
    throw new Error(data.error || ('HTTP ' + response.status));
  }
  return data;
}

function setText(id, text) {
  $(id).textContent = text;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '—';
  return Number(value).toLocaleString();
}

function formatTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function showLogin() {
  $('login').classList.remove('hidden');
  $('app').classList.add('hidden');
}

function showApp() {
  $('login').classList.add('hidden');
  $('app').classList.remove('hidden');
}

function renderBalance(payload) {
  const balance = payload.balance || {};
  ['gp', 'credits', 'hath'].forEach((name) => {
    setText(name, formatNumber(balance[name]));
    const source = balance.sources && balance.sources[name];
    setText(name + '-source', source ? 'from ' + (SOURCE_LABELS[source] || source) : '');
  });

  setText('balance-at', formatTime(payload.balance_at));

  const debug = $('debug');
  const lines = [];
  if (balance.error) lines.push(balance.error);
  (balance.debug || []).forEach((line) => lines.push(line));
  if (lines.length && (!balance.gp || !balance.credits)) {
    debug.classList.remove('hidden');
    setText('debug-text', lines.join('\n'));
  } else {
    debug.classList.add('hidden');
    setText('debug-text', '');
  }
}

function renderCookie(payload) {
  const cookie = payload.cookie || {};
  setText('cookie-masked', payload.configured ? cookie.masked : 'Not configured');
  const list = $('cookie-expiry');
  list.textContent = '';
  (cookie.expires || []).forEach((entry) => {
    const item = document.createElement('li');
    const name = Array.isArray(entry) ? entry[0] : String(entry);
    const expires = Array.isArray(entry) ? entry[1] : '';
    item.textContent = name + ': ' + expires;
    list.appendChild(item);
  });
}

function renderHistory(payload) {
  const body = $('history');
  body.textContent = '';
  const runs = payload.runs || [];
  if (!runs.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.className = 'muted';
    cell.textContent = 'No check-ins recorded yet.';
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  runs.forEach((run) => {
    const row = document.createElement('tr');
    const balance = run.balance || {};
    const values = [
      formatTime(run.ts),
      run.trigger || '',
      RESULT_LABELS[run.result] || run.result || '',
      formatNumber(balance.gp),
      formatNumber(balance.credits),
      run.message || '',
    ];
    values.forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 3 || index === 4) cell.className = 'numeric';
      if (index === 5) {
        cell.className = 'message';
        cell.title = value;
      }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
}

function render(payload) {
  setText('version', payload.version ? 'v' + payload.version : '');
  setText('next-run', payload.next_run ? formatTime(payload.next_run) : '—');
  setText('schedule', (payload.schedule || []).join(', ') || '—');
  setText('proxy', payload.proxy_configured ? 'Configured' : 'Not configured');

  const latest = (payload.runs || [])[0];
  if (latest) {
    const label = RESULT_LABELS[latest.result] || latest.result;
    const time = formatTime(latest.ts);
    setText('last-result', label + ' — ' + time);
  } else {
    setText('last-result', '—');
  }

  $('run').disabled = Boolean(payload.running);
  setText('run-message', payload.running ? 'Check-in in progress…' : '');

  renderBalance(payload);
  renderCookie(payload);
  renderHistory(payload);

  if (payload.schedule_error) {
    setText('schedule', payload.schedule_error);
  }
}

async function load() {
  try {
    const payload = await api('/api/state');
    if (!payload.authenticated) {
      showLogin();
      return;
    }
    showApp();
    render(payload);
    if (payload.running) watchRun();
  } catch (error) {
    showLogin();
  }
}

function watchRun() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const payload = await api('/api/state');
      if (!payload.authenticated) {
        clearInterval(pollTimer);
        pollTimer = null;
        showLogin();
        return;
      }
      render(payload);
      if (!payload.running) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    } catch (error) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }, 2000);
}

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  setText('login-error', '');
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ password: $('password').value }),
    });
    $('password').value = '';
    await load();
  } catch (error) {
    setText('login-error', error.message);
  }
});

$('logout').addEventListener('click', async () => {
  try {
    await api('/api/logout', { method: 'POST', body: '{}' });
  } catch (error) {
    // Ignore: the page reloads into the login view regardless.
  }
  showLogin();
});

$('run').addEventListener('click', async () => {
  setText('run-message', '');
  try {
    await api('/api/run', { method: 'POST', body: '{}' });
    $('run').disabled = true;
    setText('run-message', 'Check-in in progress…');
    watchRun();
  } catch (error) {
    setText('run-message', error.message);
  }
});

$('cookie-save').addEventListener('click', async () => {
  const message = $('cookie-message');
  message.textContent = '';
  message.className = 'small';
  try {
    await api('/api/cookie', {
      method: 'POST',
      body: JSON.stringify({ cookie: $('cookie-input').value }),
    });
    $('cookie-input').value = '';
    message.textContent = 'Cookie saved.';
    message.classList.add('ok');
    await load();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add('error');
  }
});

load();
setInterval(load, 30000);
