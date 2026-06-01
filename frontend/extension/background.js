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
});

// Sync on install
chrome.runtime.onInstalled.addListener(() => fetchProfile());
