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

    /* Skip file inputs — browsers block setting their value for security */
    if (el.type === 'file') return false;

    try {
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
    } catch (e) {
      console.warn('[JobPilot] Could not set value on', el.tagName, el.type, ':', e.message);
      return false;
    }
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
          () => document.getElementById('first_name'),
          () => findByName('job_application[first_name]'),
          () => findByName('first_name'),
          () => findFieldFuzzy(['first_name', 'first-name', 'firstname', 'given-name', 'first name']),
          () => findByLabel('First Name'),
        ],
      },
      {
        value: profile.last_name,
        selectors: [
          () => document.getElementById('last_name'),
          () => findByName('job_application[last_name]'),
          () => findByName('last_name'),
          () => findFieldFuzzy(['last_name', 'last-name', 'lastname', 'family-name', 'last name']),
          () => findByLabel('Last Name'),
        ],
      },
      {
        value: profile.email,
        selectors: [
          () => document.getElementById('email'),
          () => findByName('job_application[email]'),
          () => findByName('email'),
          () => findFieldFuzzy(['email', 'e-mail', 'email_address']),
          () => findByLabel('Email'),
        ],
      },
      {
        value: profile.phone,
        selectors: [
          () => document.getElementById('phone'),
          () => findByName('job_application[phone]'),
          () => findByName('phone'),
          () => findFieldFuzzy(['phone', 'tel', 'mobile', 'phone_number']),
          () => findByLabel('Phone'),
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
      {
        value: 'United States',
        selectors: [
          () => document.getElementById('country'),
          () => findFieldFuzzy(['country']),
          () => findByLabel('Country'),
        ],
        isSelect: true,
        selectTerms: ['united states', 'us', 'usa'],
      },
      {
        value: p => `${p.city || ''}, ${p.state || ''}`.replace(/^, |, $/, '') || 'California, United States',
        selectors: [
          () => document.getElementById('candidate-location'),
          () => findFieldFuzzy(['candidate-location', 'location']),
          () => findByLabel('Location'),
        ],
      },
    ];

    for (const entry of fieldMap) {
      const val = typeof entry.value === 'function' ? entry.value(profile) : entry.value;
      if (!val) continue;
      for (const findFn of entry.selectors) {
        const el = findFn();
        if (el && isVisible(el) && !isHoneypot(el)) {
          /* Skip already-filled fields (but allow selects at index 0) */
          if (el.tagName !== 'SELECT' && el.value) continue;
          if (el.tagName === 'SELECT' && el.selectedIndex > 0) continue;

          if (el.tagName === 'SELECT' || entry.isSelect) {
            const terms = entry.selectTerms || [val.toLowerCase()];
            let ok = false;
            for (const term of terms) {
              if (selectOption(el, term)) { ok = true; break; }
            }
            if (ok) { filled++; break; }
          } else {
            if (setNativeValue(el, val)) { filled++; break; }
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

  /* ── INTELLIGENT ANSWER ENGINE ────────────────────────────────────────
     Pattern-matched answers for 100+ common screening questions.
     Each rule: [pattern_test_function, answer_or_answer_function]
     Order matters — first match wins. */

  function buildSmartAnswers(profile) {
    const p = profile;
    const linkedin = p.linkedin || '';
    const website = p.website || '';
    const github = p.github || '';

    /* Each entry: [test(lowercaseQuestion) => bool, answer string or select-friendly values] */
    return [
      /* ── How did you hear ─────────────────────────────────────── */
      [q => q.includes('how did you hear') || q.includes('how did you find') || q.includes('how did you learn') || q.includes('where did you hear') || q.includes('where did you find') || (q.includes('source') && q.includes('hear')),
        { text: 'Google Search', select: ['google', 'search engine', 'career page', 'company website', 'job board', 'online', 'internet'] }],

      /* ── Current / Recent Company ─────────────────────────────── */
      [q => (q.includes('current') || q.includes('recent') || q.includes('present')) && q.includes('company'),
        { text: 'University of Washington' }],
      [q => (q.includes('current') || q.includes('recent') || q.includes('present')) && q.includes('employer'),
        { text: 'University of Washington' }],
      [q => (q.includes('current') || q.includes('recent')) && q.includes('title'),
        { text: 'Product Lead - Starlink Satellite Data Platform' }],

      /* ── Work Authorization ───────────────────────────────────── */
      [q => (q.includes('authorized') || q.includes('authorised') || q.includes('legally')) && q.includes('work'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('sponsorship') || (q.includes('visa') && q.includes('sponsor')),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('require visa') || q.includes('require work visa') || q.includes('immigration'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('visa status') || q.includes('current visa') || q.includes('immigration status'),
        { text: 'F-1 Student (OPT/STEM OPT eligible)', select: ['f-1', 'opt', 'student'] }],
      [q => q.includes('cpt') || q.includes('curricular practical'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('opt') && !q.includes('option'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('h-1b') || q.includes('h1b'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('export control') || q.includes('itar') || q.includes('ear'),
        { text: 'None of the Above', select: ['none', 'no', 'not applicable'] }],
      [q => q.includes('security clearance'),
        { text: 'No', select: ['no', 'none', 'not applicable'] }],

      /* ── Previously worked / interviewed ──────────────────────── */
      [q => q.includes('previously') && (q.includes('work') || q.includes('employ')),
        { text: 'No', select: ['no'] }],
      [q => q.includes('interviewed') && (q.includes('before') || q.includes('previously') || q.includes('company')),
        { text: 'No', select: ['no'] }],
      [q => q.includes('know anyone') || q.includes('know somebody') || (q.includes('employee') && q.includes('refer')),
        { text: 'No', select: ['no'] }],
      [q => q.includes('family member') || q.includes('relative') || q.includes('related to'),
        { text: 'No', select: ['no'] }],
      [q => q.includes('non-compete') || q.includes('noncompete') || q.includes('non compete'),
        { text: 'No', select: ['no'] }],
      [q => q.includes('acquired') && q.includes('company'),
        { text: 'No', select: ['no'] }],
      [q => q.includes('applied') && (q.includes('before') || q.includes('previously')),
        { text: 'No', select: ['no'] }],

      /* ── Experience ───────────────────────────────────────────── */
      [q => q.includes('years') && q.includes('experience') && q.includes('product'),
        { text: '3+', select: ['3', '4', '5', '3-5', '3+', '2-4'] }],
      [q => q.includes('years') && q.includes('experience') && (q.includes('software') || q.includes('tech') || q.includes('industry')),
        { text: '6+', select: ['6', '7', '5+', '6+', '5-7', '6-8'] }],
      [q => q.includes('years') && q.includes('experience'),
        { text: String(p.years_experience || '6'), select: ['6', '5+', '6+'] }],

      /* ── Education ────────────────────────────────────────────── */
      [q => q.includes('highest') && (q.includes('degree') || q.includes('education') || q.includes('level')),
        { text: "Master's Degree", select: ["master", "ms", "graduate", "master's"] }],
      [q => q.includes('university') || q.includes('school') || q.includes('college'),
        { text: 'University of Washington' }],
      [q => (q.includes('major') || q.includes('field of study') || q.includes('area of study')),
        { text: 'Information Management (MSIM)' }],
      [q => q.includes('gpa'),
        { text: '3.84' }],
      [q => q.includes('graduation') && (q.includes('year') || q.includes('date')),
        { text: 'June 2026', select: ['2026'] }],

      /* ── Salary & Start ───────────────────────────────────────── */
      [q => q.includes('salary') || q.includes('compensation') || q.includes('pay expectation'),
        { text: 'Open to discussing total compensation based on role scope, level, location, and benefits.' }],
      [q => q.includes('start date') || q.includes('earliest') && q.includes('start') || q.includes('when can you'),
        { text: '2 weeks from offer acceptance' }],

      /* ── Relocation & Location ────────────────────────────────── */
      [q => q.includes('relocat'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('hybrid'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('onsite') || q.includes('on-site') || q.includes('in office') || q.includes('in-office'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('remote') && (q.includes('comfortable') || q.includes('willing') || q.includes('open')),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('time zone') || q.includes('timezone'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('located') && (q.includes('us') || q.includes('united states')),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('current location') || q.includes('where are you located') || q.includes('current city'),
        { text: 'California, United States' }],

      /* ── Demographics / EEO ───────────────────────────────────── */
      [q => q.includes('gender') && (q.includes('identity') || q.includes('identify')),
        { text: 'Female', select: ['female', 'woman', 'cisgender woman'] }],
      [q => q.includes('gender') || q.includes('sex'),
        { text: 'Female', select: ['female', 'woman'] }],
      [q => q.includes('transgender'),
        { text: 'No', select: ['no'] }],
      [q => q.includes('sexual orientation'),
        { text: 'Heterosexual', select: ['heterosexual', 'straight'] }],
      [q => q.includes('pronoun'),
        { text: 'She/Her', select: ['she', 'she/her', 'she/her/hers'] }],
      [q => q.includes('ethnicit') || (q.includes('race') && !q.includes('embrace')),
        { text: 'South Asian', select: ['south asian', 'asian', 'asian (not hispanic or latino)'] }],
      [q => q.includes('veteran') || q.includes('military') || q.includes('served'),
        { text: 'No military service', select: ['no military', 'not a protected veteran', 'i am not', 'no', 'not a veteran'] }],
      [q => q.includes('disability') || q.includes('disabled') || q.includes('ada'),
        { text: 'No, I do not have a disability, or have a history/record of having a disability', select: ['no, i do not', 'no', 'do not have a disability', 'no disability'] }],

      /* ── Background / Compliance ──────────────────────────────── */
      [q => q.includes('background check'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('drug') && (q.includes('screen') || q.includes('test')),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('assessment') || q.includes('aptitude test') || q.includes('coding challenge'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('employment verification') || q.includes('verify employment'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('reference'),
        { text: 'Yes, upon request', select: ['yes'] }],
      [q => q.includes('currently employed'),
        { text: 'Yes', select: ['yes'] }],

      /* ── Skills & Tools ───────────────────────────────────────── */
      [q => q.includes('programming') && q.includes('language'),
        { text: 'Python, JavaScript, TypeScript, SQL' }],
      [q => q.includes('pm tool') || q.includes('product management tool'),
        { text: 'Jira, Figma, Amplitude, Mixpanel, VWO (A/B Testing)' }],
      [q => q.includes('sql'),
        { text: 'Basic to Intermediate', select: ['intermediate', 'basic', 'yes'] }],
      [q => q.includes('cloud') && q.includes('platform'),
        { text: 'AWS (EC2, S3, CloudFront)' }],
      [q => q.includes('agile') || q.includes('scrum'),
        { text: 'Yes', select: ['yes'] }],

      /* ── Links ────────────────────────────────────────────────── */
      [q => q.includes('linkedin'),
        { text: linkedin }],
      [q => q.includes('github'),
        { text: github }],
      [q => q.includes('portfolio') || q.includes('personal website') || q.includes('personal site'),
        { text: website }],
      [q => q.includes('website') || q.includes('url') || q.includes('online presence'),
        { text: website || linkedin }],

      /* ── Motivation / Why ─────────────────────────────────────── */
      [q => q.includes('why') && (q.includes('interest') || q.includes('role') || q.includes('position') || q.includes('apply')),
        { text: 'The role aligns with my background in product management, software engineering, and AI-driven products. I am excited about building products that solve complex customer and business problems at scale.' }],
      [q => q.includes('why') && (q.includes('leav') || q.includes('looking') || q.includes('change')),
        { text: 'I am pursuing opportunities that provide greater scope, impact, and long-term growth aligned with my product leadership goals.' }],
      [q => q.includes('strength') || q.includes('strong fit') || q.includes('what makes you'),
        { text: 'I combine product management, engineering, analytics, UX, and customer-facing experience, enabling me to translate business needs into scalable product solutions.' }],
      [q => q.includes('describe yourself') || q.includes('about yourself') || q.includes('tell us about you'),
        { text: 'Product leader with a software engineering foundation who specializes in building data-driven and AI-enabled products.' }],

      /* ── Catch-all Yes/No for common boolean questions ─────── */
      [q => q.includes('18 years') || q.includes('over 18') || q.includes('at least 18'),
        { text: 'Yes', select: ['yes'] }],
      [q => q.includes('agree') && (q.includes('terms') || q.includes('condition') || q.includes('privacy')),
        { text: 'Yes', select: ['yes'] }],
    ];
  }

  /** Handle ALL custom/screening questions — both Greenhouse-style and generic. */
  function fillCustomQuestions(profile) {
    const smartAnswers = buildSmartAnswers(profile);

    /* ── Step 1: Collect ALL question fields on the page ───────── */
    /* Greenhouse specific */
    const ghFields = document.querySelectorAll(
      'input[name*="answers_attributes"], textarea[name*="answers_attributes"], select[name*="answers_attributes"]'
    );

    /* Generic: any labeled input/select/textarea that's a "question" */
    const allFields = document.querySelectorAll(
      'input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), textarea, select'
    );

    const questionsToAsk = [];
    const fieldsByQuestion = {};
    const processedFields = new Set();

    /* Helper: get the question text for a field */
    function getQuestionText(field) {
      /* Check closest label */
      const id = field.id;
      if (id) {
        const label = document.querySelector(`label[for="${id}"]`);
        if (label) return label.textContent.trim();
      }
      /* Check parent containers for label */
      const container = field.closest('.field, .field-group, [class*="question"], [class*="field"], [class*="form-group"], [class*="form__field"], [role="group"]');
      if (container) {
        const label = container.querySelector('label, legend, [class*="label"], [class*="question-text"]');
        if (label) return label.textContent.trim();
      }
      /* Check wrapping label */
      const parentLabel = field.closest('label');
      if (parentLabel) return parentLabel.textContent.trim();
      /* Aria label */
      const ariaLabel = field.getAttribute('aria-label');
      if (ariaLabel) return ariaLabel.trim();
      /* Placeholder as last resort */
      if (field.placeholder) return field.placeholder.trim();
      return '';
    }

    /* Collect Greenhouse custom question fields */
    for (const field of ghFields) {
      if (!isVisible(field) || field.value || field.type === 'file') continue;
      const qText = getQuestionText(field);
      if (qText && qText.length > 3) {
        questionsToAsk.push(qText);
        fieldsByQuestion[qText] = field;
        processedFields.add(field);
      }
    }

    /* Collect ALL other unfilled question fields */
    for (const field of allFields) {
      if (processedFields.has(field)) continue;
      if (!isVisible(field) || field.type === 'file') continue;
      if (field.value && field.tagName !== 'SELECT') continue;
      if (field.tagName === 'SELECT' && field.selectedIndex > 0) continue;

      const qText = getQuestionText(field);
      if (qText && qText.length > 3) {
        /* Skip fields already handled by the main fillFields (name, email, phone, etc.) */
        const skip = ['first name', 'last name', 'email', 'phone', 'resume', 'cover letter',
                      'country', 'location', 'city', 'state', 'zip', 'address', 'preferred first'];
        const lower = qText.toLowerCase();
        if (skip.some(s => lower.startsWith(s) || lower === s)) continue;

        questionsToAsk.push(qText);
        fieldsByQuestion[qText] = field;
        processedFields.add(field);
      }
    }

    if (questionsToAsk.length === 0) return;
    console.log(`[JobPilot] Found ${questionsToAsk.length} screening questions`);

    /* ── Step 2: Match questions against smart answers ─────────── */
    const answered = {};
    const unanswered = [];

    for (const qText of questionsToAsk) {
      const lower = qText.toLowerCase().replace(/\s+/g, ' ').replace(/[*]/g, '').trim();
      let matched = false;

      for (const [test, answerData] of smartAnswers) {
        if (test(lower)) {
          const field = fieldsByQuestion[qText];
          const answer = typeof answerData === 'string' ? { text: answerData } : answerData;

          if (field.tagName === 'SELECT') {
            /* Try select-friendly values first, then text */
            const selectTerms = answer.select || [answer.text.toLowerCase()];
            let selected = false;
            for (const term of selectTerms) {
              if (selectOption(field, term)) { selected = true; break; }
            }
            if (selected) { matched = true; answered[qText] = true; }
          } else if (field.type === 'radio') {
            /* Handle radio button groups */
            const name = field.name;
            const radios = name ? document.querySelectorAll(`input[name="${name}"]`) : [field];
            const terms = answer.select || [answer.text.toLowerCase()];
            for (const radio of radios) {
              const lbl = radio.closest('label')?.textContent?.trim()?.toLowerCase() || radio.value?.toLowerCase() || '';
              if (terms.some(t => lbl.includes(t))) {
                radio.click();
                matched = true;
                answered[qText] = true;
                break;
              }
            }
          } else {
            if (answer.text && setNativeValue(field, answer.text)) {
              matched = true;
              answered[qText] = true;
            }
          }
          break; /* First match wins */
        }
      }

      if (!matched) {
        unanswered.push(qText);
      }
    }

    console.log(`[JobPilot] Answered ${Object.keys(answered).length} questions locally, ${unanswered.length} need API`);

    /* ── Step 3: For unanswered questions, try the answer bank API ── */
    if (unanswered.length > 0) {
      const company = detectCompany();
      const roleTitle = detectRoleTitle();

      const bankPromises = unanswered.map(qText =>
        new Promise(resolve => {
          chrome.runtime.sendMessage({ action: 'lookupAnswer', question: qText }, (resp) => {
            resolve({ question: qText, answer: resp?.ok && resp.answer ? resp.answer : null });
          });
        })
      );

      Promise.all(bankPromises).then(bankResults => {
        const stillUnanswered = [];

        for (const { question, answer } of bankResults) {
          if (answer) {
            const field = fieldsByQuestion[question];
            if (field && isVisible(field) && !field.value) {
              if (field.tagName === 'SELECT') selectOption(field, answer);
              else setNativeValue(field, answer);
            }
          } else {
            stillUnanswered.push(question);
          }
        }

        /* Step 4: Final fallback — smart answer API */
        if (stillUnanswered.length > 0) {
          console.log(`[JobPilot] ${stillUnanswered.length} questions sent to smart answer API:`, stillUnanswered);
          chrome.runtime.sendMessage({
            action: 'getSmartAnswers',
            questions: stillUnanswered,
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
      console.log('[JobPilot] No profile data — set up your profile at https://hire.shreevaidya.com/profile');
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
