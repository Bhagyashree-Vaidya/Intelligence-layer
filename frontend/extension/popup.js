/*  JobPilot — Extension popup logic v2.1
    Works on ANY job application page — ATS platforms + company career sites.  */

const statusEl = document.getElementById('status');
const profileEl = document.getElementById('profile-info');
const resumeEl = document.getElementById('resume-info');
const fillBtn = document.getElementById('fill-btn');

/* Always show "Fill This Page" — the user knows when they're on a job page.
   The content script itself checks for forms before filling. */

chrome.runtime.sendMessage({ action: 'getProfile' }, (resp) => {
  if (resp?.ok && resp.profile) {
    const p = resp.profile;
    statusEl.className = 'status ok';
    statusEl.innerHTML = '<div class="dot green"></div> Connected to JobPilot server';

    profileEl.style.display = 'block';
    profileEl.innerHTML = `
      <strong>${p.first_name || ''} ${p.last_name || ''}</strong><br>
      ${p.email || '<em>No email set</em>'}<br>
      ${p.phone || ''}${p.linkedin ? '<br>' + p.linkedin : ''}
    `;

    if (resp.default_resume_name) {
      resumeEl.style.display = 'block';
      resumeEl.innerHTML = `<i class="fa-solid fa-file-pdf"></i> ${resp.default_resume_name}`;
    }

    /* Show fill button whenever connected (user decides when to use it) */
    fillBtn.style.display = 'block';
  } else {
    statusEl.className = 'status err';
    statusEl.innerHTML = '<div class="dot red"></div> Cannot reach server — is JobPilot running?';
  }
});

fillBtn.addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      files: ['content.js']
    });
    window.close();
  });
});

// ── Night Shift queue runner ────────────────────────────────────────────────
const nsBtn = document.getElementById('nightshift-btn');
const nsLabel = document.getElementById('ns-label');
const nsProgress = document.getElementById('ns-progress');

// Show the button with a live count of queued jobs.
chrome.runtime.sendMessage({ action: 'getNightShiftQueue' }, (resp) => {
  if (resp?.ok && resp.queue && resp.queue.length > 0) {
    nsBtn.style.display = 'block';
    nsLabel.textContent = `Run Night Shift Queue (${resp.queue.length})`;
  }
});

// Live progress updates while the queue runs.
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'nightShiftProgress') {
    nsProgress.style.display = 'block';
    nsProgress.innerHTML = `Filling ${msg.index}/${msg.total}: <strong>${msg.company}</strong> — ${msg.title || ''}`;
  }
});

nsBtn.addEventListener('click', () => {
  nsBtn.disabled = true;
  nsLabel.textContent = 'Running…';
  nsProgress.style.display = 'block';
  nsProgress.textContent = 'Starting Night Shift…';
  chrome.runtime.sendMessage({ action: 'runNightShiftQueue' }, (resp) => {
    if (resp?.ok) {
      nsProgress.innerHTML = `Done: <strong>${resp.filled} filled</strong>, ${resp.errored} errored. Review each open tab, upload your resume, and submit.`;
      nsLabel.textContent = 'Night Shift complete';
    } else {
      nsProgress.textContent = `Error: ${resp?.error || 'unknown'}`;
      nsBtn.disabled = false;
      nsLabel.textContent = 'Retry Night Shift Queue';
    }
  });
});
