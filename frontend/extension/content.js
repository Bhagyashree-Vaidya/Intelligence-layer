/*  JobPilot — Content Script v2
    Auto-fills Greenhouse, Lever, Ashby, and generic ATS application forms.
    Uses exact Greenhouse `name` attributes first, then fuzzy fallbacks.
    Includes anti-detection: human-like typing delays, honeypot avoidance.  */

(() => {
  'use strict';

  const FILLED_MARKER = 'data-jobpilot-filled';
  if (document.documentElement.hasAttribute(FILLED_MARKER)) return;

  /* ── Anti-Detection Helpers ─────────────────────────────────────────── */

  function randomDelay(min = 30, max = 120) {
    return new Promise(r => setTimeout(r, min + Math.random() * (max - min)));
  }

  function isVisible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && style.opacity !== '0'
      && el.offsetWidth > 0
      && el.offsetHeight > 0;
  }

  function isHoneypot(el) {
    /* Honeypot fields: hidden inputs meant to catch bots */
    if (!isVisible(el)) return true;
    const name = (el.name || '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    const cls = (el.className || '').toLowerCase();
    const traps = ['honeypot', 'trap', 'hp_', 'bot', 'website_url_trap'];
    return traps.some(t => name.includes(t) || id.includes(t) || cls.includes(t));
  }

  /* ── Value Setting (React-compatible) ───────────────────────────────── */

  function setNativeValue(el, value) {
    if (isHoneypot(el)) return false;

    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;

    if (nativeSetter) {
      nativeSetter.call(el, value);
    } else {
      el.value = value;
    }

    /* Dispatch events in the order a real user would trigger them */
    el.dispatchEvent(new Event('focus', { bubbles: true }));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
    return true;
  }

  function selectOption(selectEl, value) {
    if (!value || isHoneypot(selectEl)) return false;
    const lower = value.toLowerCase().trim();

    /* Try exact match first, then partial */
    for (const opt of selectEl.options) {
      const txt = opt.text.toLowerCase().trim();
      const val = opt.value.toLowerCase().trim();
      if (txt === lower || val === lower) {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    for (const opt of selectEl.options) {
      if (opt.text.toLowerCase().includes(lower) || opt.value.toLowerCase().includes(lower)) {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    return false;
  }

  function setCheckbox(el, checked) {
    if (el.checked !== checked) {
      el.checked = checked;
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new Event('click', { bubbles: true }));
    }
  }

  /* ── Field Discovery ────────────────────────────────────────────────── */

  /** Find by exact Greenhouse `name` attribute — most reliable. */
  function findByName(name) {
    return document.querySelector(`[name="${name}"]`);
  }

  /** Find by label text → for attribute → element. */
  function findByLabel(labelText) {
    const lower = labelText.toLowerCase();
    for (const label of document.querySelectorAll('label')) {
      if (label.textContent.toLowerCase().includes(lower)) {
        const forId = label.getAttribute('for');
        if (forId) {
          const el = document.getElementById(forId);
          if (el && isVisible(el)) return el;
        }
        const child = label.querySelector('input, textarea, select');
        if (child && isVisible(child)) return child;
      }
    }
    return null;
  }

  /** Find by aria-label or aria-describedby text. */
  function findByAria(text) {
    const lower = text.toLowerCase();
    for (const el of document.querySelectorAll('input, textarea, select')) {
      const aria = (el.getAttribute('aria-label') || '').toLowerCase();
      if (aria.includes(lower) && isVisible(el)) return el;
    }
    return null;
  }

  /** Fuzzy search: id, name, autocomplete, placeholder, then label. */
  function findFieldFuzzy(keywords) {
    for (const kw of keywords) {
      const lower = kw.toLowerCase();
      for (const el of document.querySelectorAll('input, textarea, select')) {
        if (!isVisible(el) || isHoneypot(el)) continue;
        const id = (el.id || '').toLowerCase();
        const name = (el.name || '').toLowerCase();
        const auto = (el.autocomplete || '').toLowerCase();
        const ph = (el.placeholder || '').toLowerCase();
        if (id.includes(lower) || name.includes(lower) ||
            auto.includes(lower) || ph.includes(lower)) {
          return el;
        }
      }
    }
    for (const kw of keywords) {
      const el = findByLabel(kw) || findByAria(kw);
      if (el) return el;
    }
    return null;
  }

  /** Greenhouse custom questions: label text → for → answer input. */
  function findCustomQuestion(questionText) {
    const lower = questionText.toLowerCase();
    for (const label of document.querySelectorAll('label')) {
      if (label.textContent.toLowerCase().includes(lower)) {
        const forId = label.getAttribute('for');
        if (forId) return document.getElementById(forId);
        return label.closest('.field')?.querySelector('input, textarea, select');
      }
    }
    return null;
  }

  /* ── Field Filling ──────────────────────────────────────────────────── */

  function fillFields(profile) {
    let filled = 0;

    /*
     * Priority order for each field:
     *   1. Exact Greenhouse `name` selector
     *   2. Common ATS name patterns
     *   3. Fuzzy keyword search (id, placeholder, label)
     */
    const fieldMap = [
      {
        value: profile.first_name,
        selectors: [
          () => findByName('job_application[first_name]'),
          () => findByName('first_name'),
          () => findFieldFuzzy(['first_name', 'first-name', 'firstname', 'given-name', 'first name']),
        ],
      },
      {
        value: profile.last_name,
        selectors: [
          () => findByName('job_application[last_name]'),
          () => findByName('last_name'),
          () => findFieldFuzzy(['last_name', 'last-name', 'lastname', 'family-name', 'last name']),
        ],
      },
      {
        value: profile.email,
        selectors: [
          () => findByName('job_application[email]'),
          () => findByName('email'),
          () => findFieldFuzzy(['email', 'e-mail', 'email_address']),
        ],
      },
      {
        value: profile.phone,
        selectors: [
          () => findByName('job_application[phone]'),
          () => findByName('phone'),
          () => findFieldFuzzy(['phone', 'tel', 'mobile', 'phone_number']),
        ],
      },
      {
        value: profile.linkedin,
        selectors: [
          () => findFieldFuzzy(['linkedin', 'linked_in', 'linkedin_profile', 'linkedin url']),
          () => findByLabel('LinkedIn'),
          () => findByLabel('LinkedIn Profile'),
        ],
      },
      {
        value: profile.website,
        selectors: [
          () => findFieldFuzzy(['website', 'portfolio', 'personal_url', 'url', 'personal website']),
          () => findByLabel('Website'),
          () => findByLabel('Portfolio'),
        ],
      },
      {
        value: profile.github,
        selectors: [
          () => findFieldFuzzy(['github', 'github_url', 'github profile']),
          () => findByLabel('GitHub'),
        ],
      },
      {
        value: profile.address,
        selectors: [
          () => findFieldFuzzy(['address', 'street', 'street_address']),
          () => findByLabel('Street Address'),
        ],
      },
      {
        value: profile.city,
        selectors: [
          () => findFieldFuzzy(['city']),
        ],
      },
      {
        value: profile.state,
        selectors: [
          () => findFieldFuzzy(['state', 'province', 'region']),
        ],
      },
      {
        value: profile.zip_code,
        selectors: [
          () => findFieldFuzzy(['zip', 'postal', 'zip_code', 'postal_code']),
        ],
      },
      {
        value: profile.current_company,
        selectors: [
          () => findByLabel('Current Company'),
          () => findByLabel('Current Employer'),
          () => findFieldFuzzy(['current_company', 'company_name', 'employer']),
        ],
      },
      {
        value: profile.current_title,
        selectors: [
          () => findByLabel('Current Title'),
          () => findByLabel('Job Title'),
          () => findFieldFuzzy(['current_title', 'job_title', 'current title']),
        ],
      },
    ];

    for (const { value, selectors } of fieldMap) {
      if (!value) continue;
      for (const findFn of selectors) {
        const el = findFn();
        if (el && isVisible(el) && !isHoneypot(el) && !el.value) {
          if (el.tagName === 'SELECT') {
            if (selectOption(el, value)) { filled++; break; }
          } else {
            if (setNativeValue(el, value)) { filled++; break; }
          }
        }
      }
    }

    /* Cover letter / additional info */
    if (profile.cover_letter_default) {
      const coverSelectors = [
        () => findByName('job_application[cover_letter]'),
        () => findFieldFuzzy(['cover_letter', 'cover letter', 'additional_information', 'comments', 'additional information']),
        () => findByLabel('Cover Letter'),
        () => findByLabel('Additional Information'),
      ];
      for (const findFn of coverSelectors) {
        const el = findFn();
        if (el && isVisible(el) && !el.value) {
          if (setNativeValue(el, profile.cover_letter_default)) { filled++; break; }
        }
      }
    }

    /* EEO / Demographic dropdowns */
    const eeoMap = [
      { value: profile.gender, keywords: ['gender', 'sex'], label: 'Gender' },
      { value: profile.veteran, keywords: ['veteran'], label: 'Veteran Status' },
      { value: profile.disability, keywords: ['disability', 'disabled'], label: 'Disability Status' },
      { value: profile.race, keywords: ['race', 'ethnicity'], label: 'Race' },
    ];

    for (const { value, keywords, label } of eeoMap) {
      if (!value) continue;
      const el = findFieldFuzzy(keywords) || findByLabel(label);
      if (el && isVisible(el) && !isHoneypot(el)) {
        if (el.tagName === 'SELECT') {
          if (selectOption(el, value)) filled++;
        } else if (el.type === 'radio') {
          /* Handle radio button groups */
          const name = el.name;
          const radios = document.querySelectorAll(`input[name="${name}"]`);
          for (const radio of radios) {
            const lbl = radio.closest('label')?.textContent?.trim() || '';
            if (lbl.toLowerCase().includes(value.toLowerCase())) {
              radio.click();
              filled++;
              break;
            }
          }
        }
      }
    }

    /* Work authorization / Sponsorship */
    const authFields = [
      { value: profile.work_auth, keywords: ['authorization', 'authorised', 'work_auth', 'legally authorized', 'authorized to work'], label: 'Work Authorization' },
      { value: profile.sponsorship, keywords: ['sponsorship', 'visa', 'visa sponsorship', 'require sponsorship'], label: 'Sponsorship' },
    ];

    for (const { value, keywords, label } of authFields) {
      if (!value) continue;
      const el = findFieldFuzzy(keywords) || findByLabel(label) || findCustomQuestion(label);
      if (el && isVisible(el) && !isHoneypot(el)) {
        if (el.tagName === 'SELECT') {
          selectOption(el, value);
          filled++;
        } else if (el.type === 'radio') {
          const name = el.name;
          const radios = document.querySelectorAll(`input[name="${name}"]`);
          for (const radio of radios) {
            const lbl = radio.closest('label')?.textContent?.trim() || '';
            if (lbl.toLowerCase().includes(value.toLowerCase())) {
              radio.click();
              filled++;
              break;
            }
          }
        } else {
          if (setNativeValue(el, value)) filled++;
        }
      }
    }

    /* Greenhouse custom screening questions (answers_attributes pattern) */
    fillCustomQuestions(profile);

    return filled;
  }

  /** Detect company name from the current page. */
  function detectCompany() {
    const url = window.location.href.toLowerCase();
    /* Greenhouse: boards.greenhouse.io/{company}/jobs/... */
    let match = url.match(/boards\.greenhouse\.io\/([^/]+)/);
    if (match) return match[1];
    /* Lever: jobs.lever.co/{company}/... */
    match = url.match(/jobs\.lever\.co\/([^/]+)/);
    if (match) return match[1];
    /* Ashby: jobs.ashbyhq.com/{company}/... */
    match = url.match(/jobs\.ashbyhq\.com\/([^/]+)/);
    if (match) return match[1];
    /* Title or page meta */
    const title = document.title || '';
    const companyMeta = document.querySelector('meta[property="og:site_name"]');
    if (companyMeta) return companyMeta.content;
    return '';
  }

  /** Detect role title from the page heading. */
  function detectRoleTitle() {
    const h1 = document.querySelector('h1');
    if (h1) return h1.textContent.trim();
    const appTitle = document.querySelector('.app-title, .job-title, [class*="job-title"], [class*="posting-title"]');
    if (appTitle) return appTitle.textContent.trim();
    return '';
  }

  /** Handle Greenhouse-style custom questions — uses smart answer API + local fallback. */
  function fillCustomQuestions(profile) {
    /* Collect all custom question fields and their labels */
    const answerFields = document.querySelectorAll(
      'input[name*="answers_attributes"], textarea[name*="answers_attributes"], select[name*="answers_attributes"]'
    );

    const questionsToAsk = [];
    const fieldsByQuestion = {};

    for (const field of answerFields) {
      if (!isVisible(field) || field.value) continue;

      const container = field.closest('.field, .field-group, [class*="question"], [class*="field"]');
      const label = container?.querySelector('label') || field.closest('label');
      if (!label) continue;

      const qText = label.textContent.trim();
      questionsToAsk.push(qText);
      fieldsByQuestion[qText] = field;
    }

    if (questionsToAsk.length === 0) return;

    /* Local quick answers (no API call needed) */
    const localAnswers = {};
    for (const qText of questionsToAsk) {
      const lower = qText.toLowerCase();
      if (lower.includes('years') && lower.includes('experience')) {
        localAnswers[qText] = String(profile.years_experience || '');
      } else if (lower.includes('salary') || lower.includes('compensation')) {
        localAnswers[qText] = ''; /* Skip — user decides */
      } else if (lower.includes('start date') || lower.includes('available')) {
        localAnswers[qText] = ''; /* Skip — user decides */
      } else if (lower.includes('how did you hear') || lower.includes('referral')) {
        localAnswers[qText] = 'Online Job Board';
      } else if (lower.includes('authorized') || lower.includes('legally')) {
        localAnswers[qText] = profile.work_auth || 'Yes';
      } else if (lower.includes('sponsor')) {
        localAnswers[qText] = profile.sponsorship || 'No';
      } else if (lower.includes('linkedin')) {
        localAnswers[qText] = profile.linkedin || '';
      } else if (lower.includes('github') || lower.includes('portfolio')) {
        localAnswers[qText] = profile.github || profile.website || '';
      } else if (lower.includes('website') || lower.includes('url') || lower.includes('link')) {
        localAnswers[qText] = profile.website || profile.linkedin || '';
      }
    }

    /* Apply local answers immediately */
    for (const [qText, answer] of Object.entries(localAnswers)) {
      if (!answer) continue;
      const field = fieldsByQuestion[qText];
      if (field && isVisible(field)) {
        if (field.tagName === 'SELECT') selectOption(field, answer);
        else setNativeValue(field, answer);
      }
    }

    /* For remaining unanswered questions (like "Why this company?"),
       call the smart answer API asynchronously */
    const unanswered = questionsToAsk.filter(q => !localAnswers[q]);
    if (unanswered.length > 0) {
      const company = detectCompany();
      const roleTitle = detectRoleTitle();

      chrome.runtime.sendMessage({
        action: 'getSmartAnswers',
        questions: unanswered,
        company: company,
        role_title: roleTitle,
      }, (resp) => {
        if (!resp?.ok || !resp.answers) return;
        for (const [qText, answer] of Object.entries(resp.answers)) {
          if (!answer) continue;
          const field = fieldsByQuestion[qText];
          if (field && isVisible(field) && !field.value) {
            if (field.tagName === 'SELECT') selectOption(field, answer);
            else setNativeValue(field, answer);
          }
        }
      });
    }
  }

  /* ── Resume Upload ──────────────────────────────────────────────────── */

  async function uploadResume(resumeUrl, resumeName) {
    if (!resumeUrl) return false;

    /* Find file input — Greenhouse uses input[type="file"] inside the form */
    const fileInput = document.querySelector(
      'input[type="file"][name*="resume"], input[type="file"][name*="Resume"], input[type="file"]'
    );
    if (!fileInput) return false;

    try {
      const resp = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: 'downloadResume', url: resumeUrl }, resolve);
      });
      if (!resp?.ok) return false;

      /* Convert data URL → File → DataTransfer */
      const fetchResp = await fetch(resp.dataUrl);
      const blob = await fetchResp.blob();
      const ext = (resumeName || 'resume.pdf').split('.').pop() || 'pdf';
      const mimeTypes = {
        pdf: 'application/pdf',
        docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        doc: 'application/msword',
      };
      const file = new File([blob], resumeName, { type: mimeTypes[ext] || 'application/pdf' });

      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;

      /* Fire events in user-like order */
      fileInput.dispatchEvent(new Event('input', { bubbles: true }));
      fileInput.dispatchEvent(new Event('change', { bubbles: true }));

      return true;
    } catch (e) {
      console.warn('[JobPilot] Resume upload failed:', e);
      return false;
    }
  }

  /* ── Banner UI ──────────────────────────────────────────────────────── */

  function showBanner(filled, resumeOk) {
    /* Remove any existing banner */
    document.getElementById('jobpilot-banner')?.remove();

    const banner = document.createElement('div');
    banner.id = 'jobpilot-banner';
    banner.style.cssText = `
      position:fixed; top:16px; right:16px; z-index:999999;
      background:linear-gradient(135deg,#6366f1,#8b5cf6); color:white;
      padding:14px 20px; border-radius:14px; font-family:system-ui,-apple-system,sans-serif;
      font-size:13px; box-shadow:0 8px 32px rgba(99,102,241,.35);
      display:flex; align-items:center; gap:12px; max-width:380px;
      animation: jpSlideIn .3s ease-out;
      backdrop-filter: blur(10px);
    `;

    const style = document.createElement('style');
    style.textContent = `
      @keyframes jpSlideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:none}}
      @keyframes jpFade{from{opacity:1}to{opacity:0;transform:translateY(-8px)}}
    `;
    document.head.appendChild(style);

    const parts = [`${filled} field${filled !== 1 ? 's' : ''} filled`];
    if (resumeOk) parts.push('resume attached');

    banner.innerHTML = `
      <span style="font-size:20px">&#x1F680;</span>
      <div>
        <div style="font-weight:700;font-size:14px">JobPilot Auto-Fill</div>
        <div style="font-size:12px;opacity:.85;margin-top:3px">${parts.join(' &middot; ')} &mdash; review & submit!</div>
      </div>
      <button id="jp-close" style="
        margin-left:auto; opacity:.7; cursor:pointer; background:none;
        border:none; color:white; font-size:18px; padding:4px 8px;
        border-radius:6px; transition:opacity .15s;
      " onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=.7">&times;</button>
    `;
    document.body.appendChild(banner);

    document.getElementById('jp-close').onclick = () => {
      banner.style.animation = 'jpFade .2s ease-out forwards';
      setTimeout(() => banner.remove(), 200);
    };
    /* Auto-dismiss after 10s */
    setTimeout(() => {
      if (banner.parentNode) {
        banner.style.animation = 'jpFade .3s ease-out forwards';
        setTimeout(() => banner.remove(), 300);
      }
    }, 10000);
  }

  /* ── Main ───────────────────────────────────────────────────────────── */

  async function run() {
    /* Detect if this page has a job application form */
    const hasForm = document.querySelector('form#application_form')
      || document.querySelector('form[data-job-application]')
      || document.querySelector('#application')
      || document.querySelector('[class*="application"]')
      || document.querySelector('form input[name*="job_application"]')
      || document.querySelector('form');

    if (!hasForm) return;

    /* Extra check: must have at least one visible text input */
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
    const hasVisibleInput = Array.from(inputs).some(el => isVisible(el));
    if (!hasVisibleInput) return;

    /* Fetch profile from background */
    const data = await new Promise(resolve => {
      chrome.runtime.sendMessage({ action: 'getProfile' }, resolve);
    });

    if (!data?.ok || !data.profile) {
      console.log('[JobPilot] No profile data — set up your profile at http://127.0.0.1:8000/profile');
      return;
    }

    const profile = data.profile;

    /* Small initial delay to appear human-like */
    await randomDelay(200, 600);

    const filled = fillFields(profile);
    const resumeOk = await uploadResume(data.default_resume_url, data.default_resume_name);

    if (filled > 0 || resumeOk) {
      document.documentElement.setAttribute(FILLED_MARKER, 'true');
      showBanner(filled, resumeOk);
      console.log(`[JobPilot] Auto-filled ${filled} fields${resumeOk ? ' + resume' : ''}`);
    }
  }

  /* ── Initialization ─────────────────────────────────────────────────── */

  function init() {
    /* Wait for dynamic content to load (SPA-style ATS pages) */
    setTimeout(run, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* Watch for dynamically loaded forms (Greenhouse / Lever SPAs) */
  const observer = new MutationObserver((mutations) => {
    if (document.documentElement.hasAttribute(FILLED_MARKER)) return;
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType === 1) {
          const hasNewForm = node.tagName === 'FORM'
            || node.querySelector?.('form')
            || node.querySelector?.('input[type="text"]');
          if (hasNewForm) {
            setTimeout(run, 800);
            return;
          }
        }
      }
    }
  });

  const target = document.body || document.documentElement;
  if (target) {
    observer.observe(target, { childList: true, subtree: true });
  }

})();
