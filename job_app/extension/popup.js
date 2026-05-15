/*  JobPilot — Extension popup logic v2
    Multi-ATS support: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable  */

const statusEl = document.getElementById('status');
const profileEl = document.getElementById('profile-info');
const resumeEl = document.getElementById('resume-info');
const fillBtn = document.getElementById('fill-btn');

/* ATS domain patterns for "Fill This Page" button */
const ATS_PATTERNS = [
  'greenhouse.io',
  'lever.co',
  'ashbyhq.com',
  'myworkdayjobs.com',
  'smartrecruiters.com',
  'workable.com',
  '/jobs/',
  '/careers/',
  '/apply/',
  'job-boards',
];

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
  } else {
    statusEl.className = 'status err';
    statusEl.innerHTML = '<div class="dot red"></div> Cannot reach server — is JobPilot running?';
  }
});

/* Show "Fill This Page" if we're on a recognized ATS domain */
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const url = (tabs[0]?.url || '').toLowerCase();
  if (ATS_PATTERNS.some(p => url.includes(p))) {
    fillBtn.style.display = 'block';
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
