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

OUTREACH_SYSTEM = """You are a networking strategist for PM job seekers.

Write a short, personalized LinkedIn message (under 300 characters for connection request,
or under 1000 characters for InMail). Be genuine, specific to their post, not generic.
Reference something concrete from their post. Don't be desperate or salesy.
End with a light question or value proposition."""

COVER_LETTER_SYSTEM = """You are an expert PM career coach writing a cover letter.

Write a concise, compelling cover letter (250-400 words) that:
- Opens with a specific hook about the company/role (not "I'm writing to apply...")
- Maps the candidate's experience to the role's requirements
- Shows understanding of the company's product and challenges
- Ends with confidence, not desperation
- Uses professional but natural language (not corporate-speak)

IMPORTANT: Do NOT write a closing salutation, sign-off, or signature
(no "Sincerely", "Best", or name at the end) — a signature block is
appended automatically. End with your final body paragraph."""

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
