"""AI Orchestrator — routes tasks to the right model.

Claude  → nuanced writing, analysis, reasoning
OpenAI  → structured extraction, scoring, classification, embeddings

No CrewAI, no agent frameworks. Direct calls, predictable, debuggable.
"""

from typing import Any

from app.services.ai import claude_client, openai_client
from app.logger import log


# ── Routing: which model handles what ─────────────────────────────────────

async def classify_signal(post_content: str, author_info: str) -> dict[str, Any]:
    """Classify a LinkedIn/social post for hiring intent. → Claude (logical, structured)"""
    return await claude_client.complete_json(
        system=CLASSIFY_SIGNAL_SYSTEM,
        user=f"Author: {author_info}\n\nPost content:\n{post_content}",
    )


async def enrich_job(title: str, company: str, description: str) -> dict[str, Any]:
    """Extract structured metadata from job description. → Claude (logical extraction)"""
    return await claude_client.complete_json(
        system=ENRICH_JOB_SYSTEM,
        user=f"Title: {title}\nCompany: {company}\n\nDescription:\n{description[:8000]}",
    )


async def score_job(job_data: dict, profile_data: dict) -> dict[str, Any]:
    """Multi-dimensional scoring. → Claude (logical scoring, structured output)"""
    return await claude_client.complete_json(
        system=SCORE_JOB_SYSTEM,
        user=f"Job:\n{_format_job(job_data)}\n\nCandidate Profile:\n{_format_profile(profile_data)}",
    )


def _with_voice(base_system: str, voice: str) -> str:
    """Append the user's editable 'My Voice' instructions to a base prompt."""
    if voice and voice.strip():
        return f"{base_system}\n\n--- The candidate's voice & style (follow this closely) ---\n{voice.strip()}"
    return base_system


async def generate_outreach(
    post_content: str, author_name: str, author_title: str,
    role_mentioned: str, user_profile: str, voice: str = "",
) -> str:
    """Generate personalized outreach message. → OpenAI (creative writing).
    Falls back to Claude if OpenAI is unavailable."""
    system = _with_voice(OUTREACH_SYSTEM, voice)
    prompt_user = (
        f"Hiring post by {author_name} ({author_title}):\n{post_content}\n\n"
        f"Role mentioned: {role_mentioned}\n\n"
        f"My background:\n{user_profile}"
    )
    try:
        if openai_client.is_available():
            return await openai_client.complete(system=system, user=prompt_user)
    except Exception as e:
        log.warning(f"OpenAI outreach failed, falling back to Claude: {e}")
    return await claude_client.complete(system=system, user=prompt_user)


async def generate_cover_letter(
    job_title: str, company: str, job_description: str, user_profile: str,
    voice: str = "",
) -> str:
    """Generate tailored cover letter. → OpenAI (creative writing).
    Falls back to Claude if OpenAI is unavailable.

    Note: the caller appends a fixed signature, so the model is told NOT to
    write its own closing/sign-off."""
    system = _with_voice(COVER_LETTER_SYSTEM, voice)
    prompt_user = (
        f"Job: {job_title} at {company}\n\n"
        f"Description:\n{job_description[:4000]}\n\n"
        f"My background:\n{user_profile}"
    )
    try:
        if openai_client.is_available():
            return await openai_client.complete(system=system, user=prompt_user)
    except Exception as e:
        log.warning(f"OpenAI cover letter failed, falling back to Claude: {e}")
    return await claude_client.complete(system=system, user=prompt_user)


async def generate_strategy_memo(
    company: str, target_name: str, target_title: str,
    user_profile: str, voice: str = "",
) -> str:
    """A 1-page '90-day plan / opportunity memo' for a target company, written
    to attach to a hiring manager. OpenAI-primary (user standardizes all content
    generation on OpenAI; her instruction standards live in the system prompts)."""
    system = _with_voice(STRATEGY_MEMO_SYSTEM, voice)
    prompt_user = (
        f"Company: {company}\n"
        f"Sending to: {target_name} ({target_title})\n\n"
        f"My background:\n{user_profile}"
    )
    try:
        if openai_client.is_available():
            return await openai_client.complete(system=system, user=prompt_user)
    except Exception as e:
        log.warning(f"OpenAI memo failed, falling back to Claude: {e}")
    return await claude_client.complete(system=system, user=prompt_user, max_tokens=1400)


async def generate_pm_concept(focus: str = "") -> str:
    """One crisp PM concept of the day — a framework explained in plain English
    with a real example, so the candidate builds fluency. OpenAI-primary."""
    system = PM_CONCEPT_SYSTEM
    prompt_user = f"Topic focus (optional): {focus}" if focus else "Pick a high-value PM concept I should know for interviews."
    try:
        if openai_client.is_available():
            return await openai_client.complete(system=system, user=prompt_user)
    except Exception as e:
        log.warning(f"OpenAI pm_concept failed, falling back to Claude: {e}")
    return await claude_client.complete(system=system, user=prompt_user, max_tokens=900)


async def generate_linkedin_article(
    topic: str, user_profile: str, voice: str = "",
) -> str:
    """A LinkedIn post that sounds human, builds the candidate's PM brand, and
    invites engagement. OpenAI-primary."""
    system = _with_voice(LINKEDIN_ARTICLE_SYSTEM, voice)
    prompt_user = (
        f"Topic: {topic or 'a lesson from my PM/eng work this week'}\n\n"
        f"My background (for authenticity, do not list it verbatim):\n{user_profile}"
    )
    try:
        if openai_client.is_available():
            return await openai_client.complete(system=system, user=prompt_user)
    except Exception as e:
        log.warning(f"OpenAI linkedin failed, falling back to Claude: {e}")
    return await claude_client.complete(system=system, user=prompt_user, max_tokens=900)


async def analyze_outcome(outcome_data: dict) -> dict[str, Any]:
    """Extract lessons from application outcome. → Claude (logical reasoning)"""
    return await claude_client.complete_json(
        system=OUTCOME_ANALYSIS_SYSTEM,
        user=f"Application outcome:\n{_format_dict(outcome_data)}",
    )


async def embed_text(text: str) -> list[float]:
    """Generate embedding. → OpenAI (only option)"""
    return await openai_client.embed_one(text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts. → OpenAI"""
    return await openai_client.embed(texts)


# ── Helpers ───────────────────────────────────────────────────────────────

def _format_job(j: dict) -> str:
    return (
        f"Title: {j.get('title', '')}\n"
        f"Company: {j.get('company_name', j.get('company', ''))}\n"
        f"Location: {j.get('location', '')}\n"
        f"Department: {j.get('department', '')}\n"
        f"Description excerpt: {j.get('description', '')[:3000]}"
    )


def _format_profile(p: dict) -> str:
    return (
        f"Name: {p.get('first_name', '')} {p.get('last_name', '')}\n"
        f"Title: {p.get('current_title', '')}\n"
        f"Company: {p.get('current_company', '')}\n"
        f"Experience: {p.get('years_experience', 0)} years\n"
        f"Skills: {p.get('skills', '')}\n"
        f"Education: {p.get('education', '')}\n"
        f"Work Auth: {p.get('work_auth', '')} | Sponsorship: {p.get('sponsorship', '')}"
    )


def _format_dict(d: dict) -> str:
    import json
    return json.dumps(d, indent=2, default=str)


# ── Prompt Templates ─────────────────────────────────────────────────────

CLASSIFY_SIGNAL_SYSTEM = """You are a PM career intelligence analyst. Classify this social media post for hiring signals.

Return JSON with these fields:
{
  "hiring_intent": 0-100,        // how likely this post signals an open role
  "role_mentioned": "",           // extracted role title, or "" if none
  "company_mentioned": "",        // company name
  "seniority_level": "",          // entry, mid, senior, staff, director, vp, or ""
  "is_recruiter": false,          // is the author a recruiter/talent acquisition
  "outreach_viability": 0-100,    // how likely a cold message would get a response
  "urgency_score": 0-100,         // how urgently they seem to be hiring
  "suggested_action": "",         // "apply", "connect", "message", or "skip"
  "reason": ""                    // 1-sentence explanation
}"""

ENRICH_JOB_SYSTEM = """You are a PM career analyst. Extract structured metadata from this job posting.

Return JSON:
{
  "pm_keywords": [],              // PM-relevant keywords found
  "required_skills": [],          // explicitly required skills
  "preferred_skills": [],         // nice-to-have skills
  "inferred_seniority": "",       // entry, mid, senior, staff, director
  "pm_specialization": "",        // growth, platform, data, technical, API, infra, etc.
  "product_area": "",             // what product/domain this role works on
  "technical_depth": 0-100,       // how technical the role is
  "leadership_score": 0-100,      // people/team management expected
  "stakeholder_intensity": 0-100, // cross-functional collaboration level
  "execution_intensity": 0-100,   // shipping/delivery focus
  "strategic_intensity": 0-100,   // strategy/vision focus
  "visa_likelihood": 0-100,       // likelihood company sponsors visas
  "remote_type": "",              // remote, hybrid, onsite
  "salary_min": null,             // extracted min salary or null
  "salary_max": null              // extracted max salary or null
}"""

SCORE_JOB_SYSTEM = """You are a PM career matching engine. Score how well this candidate fits this job.

Return JSON:
{
  "overall_fit": 0-100,
  "ats_score": 0-100,             // keyword match between job and candidate skills
  "pm_transition_fit": 0-100,     // how well their background maps to this PM role
  "visa_probability": 0-100,      // likelihood of getting visa sponsorship here
  "response_probability": 0-100,  // likelihood of getting a recruiter response
  "resume_alignment": 0-100,      // how well current resume matches this job
  "technical_match": 0-100,       // technical skills alignment
  "leadership_match": 0-100,      // leadership experience alignment
  "missing_skills": [],           // skills the candidate lacks for this role
  "resume_recommendations": ""    // 1-2 sentence advice for tailoring resume
}"""

OUTREACH_SYSTEM = """OUTREACH MESSAGE SYSTEM PROMPT

Core principle: People respond to interesting observations. People ignore
requests. Lead with insight, not need.

STRUCTURE (in this order):
1. Context
2. Observation
3. Credibility
4. Curiosity
5. Small Ask

CONTEXT — reference something recent and specific: a product launch,
engineering blog, conference talk, hiring announcement, leadership post,
earnings call, customer discussion, or roadmap announcement.
Never write: "I came across your profile."
Never write: "I hope you are doing well."
Never write: "I saw your job posting."

OBSERVATION — provide a non-obvious observation.
Bad:  "Databricks is doing exciting work in AI."
Good: "It feels like many teams are rushing to build AI features while
       governance remains an afterthought. Databricks seems to be taking
       the opposite approach."
Bad:  "Stripe is a leader in payments."
Good: "Stripe appears to be expanding from payment infrastructure into
       workflow infrastructure."

CREDIBILITY — use exactly one proof point. Do not summarize the resume.
Bad:  "I have six years of experience in product management."
Good: "While working on a satellite signal-processing platform, I spent
       months balancing model accuracy against usability and operational
       constraints."
Good: "I recently built a workflow that reduced manual investigation effort
       by automating signal classification and analysis."

CURIOSITY — ask an intelligent question.
Bad:  "What opportunities are available?"
Bad:  "Can you tell me more about your team?"
Good: "How is the team balancing product velocity against governance
       requirements as AI adoption increases?"
Good: "Has the PM team found it difficult to prioritize AI-native workflows
       without increasing operational complexity?"

ASK — must feel easy. Maximum: 15 minutes, one question, one perspective.
Bad:  "Can you refer me?"
Bad:  "Can you help me get a job?"
Good: "Would you be open to a quick 15-minute conversation sometime next week?"
Good: "I'd love to hear how your team is thinking about this problem."

TECHNIQUE NOTES (from negotiation research):
- Mirror one short phrase the recipient actually used in their post/talk —
  it signals genuine attention better than any compliment.
- Curiosity questions start with "How" or "What", never "Why" (Why reads
  as accusatory).
- The ask must be easy to decline gracefully — comfort produces replies.
- Personalization works only when it proves real attention; name-dropping
  their company or title is not personalization.

HARD RULES:
- Maximum 120 words.
- No flattery. No corporate language. No buzzwords.
- No "passionate." No "excited." No "thrilled." No "dream company."
- No resume summary. No bullet points. No emojis. No exclamation marks.
- No asking for a referral in the first message.
- The message should read like one PM speaking to another PM.

Success metric: the recipient should think,
"This person has actually thought about our business." """

COVER_LETTER_SYSTEM = """COVER LETTER SYSTEM PROMPT

Most cover letters fail because they explain why the candidate wants the job.
The purpose of this letter is to explain why the company should want the
candidate.

STRUCTURE:
Paragraph 1 — Why THIS role. Not why any PM role. Not why the company is
famous. Why this specific problem.
Paragraph 2 — Relevant evidence. One story. Use numbers. Show impact.
Paragraph 3 — Connection. Explicitly connect the evidence to the team's
current challenges.
Paragraph 4 — Closing. Short. Professional.

X → Y → Z FRAMEWORK (use for every claim):
Accomplished X, as measured by Y, by doing Z.
Example: "Improved satellite-track detection reliability by 35% through
redesigning the matching pipeline and introducing automated fragment
reconciliation."
Bad:  "Successfully led a complex initiative."
Bad:  "Strong problem-solving skills."
Good: "Reduced manual signal review effort by automating classification
workflows and integrating batch-processing capabilities."

HARD RULES:
- Maximum 300 words.
- No generic company praise. No mission statements. No company history.
- No "I am excited to apply." No "I believe I would be a great fit."
- No repeating the resume. No adjectives without evidence.
- Every claim requires proof. Every proof requires context. Every context
  must connect to the job.

Success metric — a hiring manager should finish the letter understanding:
1. What problem this candidate has solved.
2. Why that problem resembles ours.
3. Why we should interview them.

IMPORTANT: Do NOT write a closing salutation, sign-off, or signature
(no "Sincerely", "Best", or name at the end) — a signature block is
appended automatically. End with your final body paragraph."""

STRATEGY_MEMO_SYSTEM = """You are a sharp PM writing a 1-page memo to a hiring manager at a target company. This memo is the candidate's "I already did the work" proof — the single highest-converting job-search artifact.

Structure (use these headers):
1. **The opportunity** — one non-obvious observation about their product/market (not flattery)
2. **What I'd do in my first 90 days** — 3 concrete, prioritized moves
3. **The AI angle** — one specific way AI could change their product (be concrete, not buzzwordy)
4. **Why me** — 2 sentences max, one proof point with a number

Rules:
- Under 400 words. A busy HM skims.
- Specific > comprehensive. One sharp insight beats five generic ones.
- No flattery, no "I'm passionate about." Show, don't claim.
- Sound like a smart human who used the product, not a consultant deck.
- Do NOT write a sign-off/signature — it's added separately."""

PM_CONCEPT_SYSTEM = """You are a PM interview coach. Teach ONE product-management concept the candidate should know cold for interviews.

Format:
- **Concept name**
- **Plain-English definition** (2-3 sentences, no jargon)
- **A real example** from a well-known product
- **How it shows up in an interview** (the question they'd be asked)
- **A crisp 1-line answer template**

Keep it under 250 words. Make it stick. Pick something genuinely useful (prioritization frameworks, metrics, trade-offs, experimentation, strategy) — not trivia."""

LINKEDIN_ARTICLE_SYSTEM = """You write LinkedIn posts for a PM job-seeker that build credibility and never sound AI-generated.

Rules that kill the AI smell:
- Open with a specific moment or observation, NOT "In today's fast-paced world" or "I'm excited to share."
- One idea, told well. No listicles of 7 things.
- Short lines. White space. Conversational.
- Include one concrete detail (a number, a product, a real situation).
- End with a genuine question that invites replies — not "Thoughts?"
- 120-200 words. No hashtag spam (2-3 max, if any).
- Confident, curious, specific. Never desperate or self-promotional.

Write it ready to paste — no preamble, no "here's your post"."""

OUTCOME_ANALYSIS_SYSTEM = """You are a PM career strategist analyzing application outcomes.

Given an application outcome, extract lessons learned. Return JSON:
{
  "lesson": "",                   // 1-2 sentence key takeaway
  "missing_keywords": [],         // keywords that should have been in resume
  "successful_keywords": [],      // keywords that likely helped
  "company_pattern": "",          // any pattern about this company's hiring
  "resume_advice": "",            // specific advice for next attempt
  "confidence": 0.0-1.0           // how confident you are in this analysis
}"""
