/*  JobPilot — background service worker.
    Fetches profile from the JobPilot server and caches it.
    Also fetches answer bank from application_answers.md for form filling.  */

const API = 'https://jobs.shreevaidya.com';

async function fetchProfile() {
  try {
    const resp = await fetch(`${API}/api/profile`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    await chrome.storage.local.set({ profile: data.profile, resumeUrl: data.default_resume_url, resumeName: data.default_resume_name, lastSync: Date.now() });
    return data;
  } catch (e) {
    console.error('[JobPilot] Could not reach server:', e.message);
    return null;
  }
}

// Refresh profile every time extension popup opens or content script asks
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'getProfile') {
    fetchProfile().then(data => {
      if (data) {
        sendResponse({ ok: true, ...data });
      } else {
        // Fall back to cached
        chrome.storage.local.get(['profile', 'resumeUrl', 'resumeName'], (items) => {
          sendResponse(items.profile ? { ok: true, profile: items.profile, default_resume_url: items.resumeUrl, default_resume_name: items.resumeName } : { ok: false });
        });
      }
    });
    return true; // async
  }

  if (msg.action === 'downloadResume') {
    fetch(`${API}${msg.url}`)
      .then(r => r.blob())
      .then(blob => {
        const reader = new FileReader();
        reader.onload = () => sendResponse({ ok: true, dataUrl: reader.result });
        reader.readAsDataURL(blob);
      })
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  if (msg.action === 'getSmartAnswers') {
    fetch(`${API}/api/answers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        questions: msg.questions || [],
        company: msg.company || '',
        role_title: msg.role_title || '',
      }),
    })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, answers: data }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  if (msg.action === 'lookupAnswer') {
    fetch(`${API}/api/answers/lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: msg.question || '' }),
    })
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, answer: data.answer, matched_key: data.matched_key }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  if (msg.action === 'getAnswerBank') {
    fetch(`${API}/api/answers/bank`)
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, sections: data.sections }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  // ── Night Shift: fetch the review queue ──────────────────────────────────
  if (msg.action === 'getNightShiftQueue') {
    fetch(`${API}/api/night-shift/queue?status=queued`)
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, queue: data.queue || [] }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  // ── Night Shift: run the queue (open each job, fill, park) ────────────────
  if (msg.action === 'runNightShiftQueue') {
    runNightShiftQueue((progress) => {
      // Stream progress to popup if it's still open (best-effort).
      chrome.runtime.sendMessage({ action: 'nightShiftProgress', ...progress }).catch(() => {});
    }).then(summary => sendResponse({ ok: true, ...summary }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
});


// ── Night Shift queue runner ───────────────────────────────────────────────
// Opens each queued job in a tab, auto-fills via content.js, marks it 'filled'
// (or 'error'), and moves on. NEVER submits — the user reviews + submits.

async function markItem(id, body) {
  try {
    await fetch(`${API}/api/night-shift/queue/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    console.error('[JobPilot] markItem failed', e);
  }
}

function waitForTabLoad(tabId, timeoutMs = 25000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => { if (!done) { done = true; resolve(ok); } };
    const listener = (id, info) => {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        // small settle delay for SPA forms to render
        setTimeout(() => finish(true), 2500);
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
    setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); finish(false); }, timeoutMs);
  });
}

async function runNightShiftQueue(onProgress) {
  const resp = await fetch(`${API}/api/night-shift/queue?status=queued`);
  const data = await resp.json();
  const queue = data.queue || [];

  let filled = 0, errored = 0;
  for (let i = 0; i < queue.length; i++) {
    const item = queue[i];
    onProgress({ index: i + 1, total: queue.length, company: item.company, title: item.title });

    if (!item.url) {
      await markItem(item.id, { status: 'error', error_message: 'No application URL' });
      errored++;
      continue;
    }

    let tab;
    try {
      tab = await chrome.tabs.create({ url: item.url, active: true });
      const loaded = await waitForTabLoad(tab.id);
      if (!loaded) throw new Error('Page load timed out');

      // Inject the existing autofill content script (fills everything but the file).
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      // Give it time to fill.
      await new Promise(r => setTimeout(r, 4000));

      await markItem(item.id, { status: 'filled', filled_at: new Date().toISOString() });
      filled++;
    } catch (e) {
      await markItem(item.id, { status: 'error', error_message: String(e).slice(0, 300) });
      errored++;
    }
    // Leave the tab OPEN so the user can review + upload resume + submit.
  }

  return { filled, errored, total: queue.length };
}

// Sync on install
chrome.runtime.onInstalled.addListener(() => fetchProfile());
