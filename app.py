import os
import re
from urllib.parse import quote_plus

import streamlit as st
from dotenv import load_dotenv

from job_search import JobSearchError, search_google_jobs, search_google_jobs_with_fallback
from resume import ResumeParseError, extract_resume_text, match_score
from suggestions import (
    SuggestionError,
    answer_career_question,
    extract_job_search_request,
    filter_jobs_for_role,
    generate_suggestions,
    local_career_answer,
)


load_dotenv()
st.set_page_config(page_title="Career Compass AI", page_icon="🧭", layout="wide")


def get_secret(name: str) -> str:
    try:
        return st.secrets.get(name, os.getenv(name, "")).strip()
    except (FileNotFoundError, KeyError):
        return os.getenv(name, "").strip()


st.markdown(
    """
    <style>
    :root {
        --ink: #17213b;
        --muted: #59647d;
        --accent: #087f72;
        --accent-dark: #075e54;
        --line: #d5e8df;
    }
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 4% 0%, rgba(86, 211, 174, .32), transparent 38rem),
            radial-gradient(ellipse at 100% 30%, rgba(255, 195, 110, .28), transparent 34rem),
            radial-gradient(ellipse at 56% 100%, rgba(116, 193, 236, .2), transparent 38rem),
            #e7f3ec;
    }
    [data-testid="stAppViewContainer"] .main .block-container {
        max-width: 1180px;
        padding: 2.2rem 2.5rem 4rem;
    }
    [data-testid="stHeader"] { background: transparent; }
    h1, h2, h3, p, label, [data-testid="stMarkdownContainer"] {
        font-family: Inter, "Segoe UI", Arial, sans-serif;
    }
    .top-nav {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: .5rem;
        margin: 0 auto 1rem;
    }
    .top-nav a {
        padding: .55rem .95rem;
        border: 1px solid #cde5d8;
        border-radius: 999px;
        background: rgba(255,255,255,.92);
        color: #17473f !important;
        font-size: .86rem;
        font-weight: 700;
        text-decoration: none !important;
        box-shadow: 0 3px 10px rgba(30, 40, 75, .05);
    }
    .top-nav a:hover {
        border-color: #49bca2;
        background: #dcf5e9;
        color: #075e54 !important;
    }
    .hero {
        text-align: center;
        margin-bottom: 1.25rem;
        padding: 2.3rem 1.2rem 2rem;
        border: 1px solid rgba(255,255,255,.35);
        border-radius: 26px;
        background: linear-gradient(118deg, #07534f 0%, #087f72 48%, #37a883 100%);
        box-shadow: 0 20px 44px rgba(13, 102, 82, .24);
    }
    .hero-kicker {
        display: inline-block;
        padding: .38rem .8rem;
        border: 1px solid rgba(255,255,255,.35);
        border-radius: 999px;
        background: rgba(255,255,255,.14);
        color: #fff;
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .04em;
    }
    .hero h1 {
        margin: .85rem 0 .45rem;
        color: #fff;
        font-size: clamp(2.1rem, 5vw, 3.25rem);
        font-weight: 780;
        letter-spacing: -.045em;
        line-height: 1.12;
    }
    .hero p {
        margin: 0 auto;
        max-width: 620px;
        color: #e5fff4;
        font-size: 1rem;
        line-height: 1.6;
    }
    [data-testid="stForm"] {
        padding: 1.35rem 1.45rem 1.1rem;
        border: 1px solid rgba(207, 229, 217, .98);
        border-radius: 22px;
        background: #fff;
        box-shadow: 0 18px 48px rgba(29, 86, 68, .13);
    }
    [data-testid="stTextInput"] label, [data-testid="stSelectbox"] label,
    [data-testid="stFileUploader"] label {
        color: #414b63;
        font-size: .86rem;
        font-weight: 650;
    }
    [data-testid="stTextInput"] input, [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 2.9rem;
        border-color: #dfe3ed;
        border-radius: 11px;
        background: #fff;
    }
    [data-testid="stTextInput"] input:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 2px rgba(8, 127, 114, .16);
    }
    [data-testid="stFormSubmitButton"] button, .stLinkButton a, [data-testid="stButton"] button {
        min-height: 2.9rem;
        border-radius: 11px;
        font-weight: 700;
        transition: transform .15s ease, box-shadow .15s ease;
    }
    [data-testid="stFormSubmitButton"] button {
        border: 0;
        background: linear-gradient(105deg, #087f72, #16a27d);
        color: #fff;
        box-shadow: 0 8px 20px rgba(8, 127, 114, .3);
    }
    [data-testid="stFormSubmitButton"] button:hover, .stLinkButton a:hover {
        transform: translateY(-1px);
        box-shadow: 0 9px 22px rgba(47, 52, 94, .13);
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--line);
        border-radius: 17px;
        background: #fff;
        box-shadow: 0 8px 24px rgba(29, 86, 68, .07);
    }
    [data-testid="stMetric"] {
        padding: .55rem .7rem;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: #effaf5;
    }
    [data-testid="stMetricValue"] { color: var(--accent-dark); }
    [data-testid="stAlert"] { border-radius: 12px; }
    [data-testid="stExpander"] {
        border-color: var(--line);
        border-radius: 13px;
        background: #fff;
    }
    .app-footer {
        margin-top: 2rem;
        padding: 1.2rem 1rem;
        border: 1px solid #cfe3d7;
        border-radius: 16px;
        background: linear-gradient(110deg, #fff, #e4f5eb 62%, #fff1d9);
        color: #47516a;
        text-align: center;
        font-size: .84rem;
        line-height: 1.6;
    }
    .app-footer strong { color: #075e54; }
    .app-footer a {
        color: #075e54 !important;
        font-weight: 700;
    }
    @media (max-width: 720px) {
        [data-testid="stAppViewContainer"] .main .block-container {
            padding: 1rem .9rem 2rem;
        }
        .top-nav { gap: .35rem; margin-bottom: .75rem; }
        .top-nav a { padding: .48rem .7rem; font-size: .78rem; }
        .hero { padding: 1.6rem .85rem 1.45rem; border-radius: 20px; }
        .hero h1 { font-size: clamp(1.85rem, 9vw, 2.45rem); }
        .hero p { font-size: .94rem; }
        [data-testid="stForm"] {
            padding: 1rem .9rem .85rem;
            border-radius: 16px;
        }
        [data-testid="stFormSubmitButton"] button,
        .stLinkButton a, [data-testid="stButton"] button {
            width: 100%;
        }
    }
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { transition: none !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <nav class="top-nav" aria-label="Page navigation">
      <a href="#search">🔎 Search</a>
      <a href="#matches">💼 Job matches</a>
      <a href="#assistant">✨ AI assistant</a>
      <a href="#job-boards">🌐 Job boards</a>
    </nav>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <span class="hero-kicker">AI-POWERED CAREER SEARCH</span>
      <h1>Find the role that moves you forward</h1>
      <p>Search opportunities, compare companies, and see how your resume lines up — all in one place.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div id="search"></div>', unsafe_allow_html=True)
with st.form("job_search_form"):
    first_row = st.columns([1.35, 1, 1], gap="medium")
    with first_row[0]:
        role = st.text_input("Role or keywords", placeholder="e.g. Gen AI Engineer")
    with first_row[1]:
        company = st.text_input("Company", placeholder="Optional · e.g. Google")
    with first_row[2]:
        domain = st.text_input("Domain", placeholder="Optional · e.g. fintech")
    second_row = st.columns([1.1, 1.1, .8], gap="medium", vertical_alignment="bottom")
    with second_row[0]:
        location = st.text_input("Location", value="India", placeholder="City, country, or remote")
    with second_row[1]:
        experience = st.selectbox(
            "Experience",
            ["Any", "Internship", "Fresher", "2 years", "1-3 years", "3-5 years", "5+ years"],
        )
    with second_row[2]:
        submitted = st.form_submit_button(
            "🔎  Find jobs", type="primary", use_container_width=True
        )

with st.expander("📄  Add a resume for match scores", expanded=False):
    uploaded_resume = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
    st.caption(
        "Resume text is processed in this session. Search for jobs to see a local match "
        "score on each listing; Gemini is not required for scoring."
    )
    if uploaded_resume is not None and get_secret("GEMINI_API_KEY"):
        use_resume_with_gemini = st.checkbox(
            "Allow Gemini to use my resume text for suggestions",
            value=False,
        )
    else:
        use_resume_with_gemini = False

if submitted:
    terms = [term.strip() for term in (role, company, domain) if term.strip()]
    if not terms:
        st.session_state["search_error"] = "Enter a role, company, or domain to search."
        st.session_state.pop("jobs", None)
        st.session_state.pop("search_query", None)
    else:
        query = " ".join(terms)
        if experience != "Any":
            query = f"{query} {experience}"
        st.session_state["search_query"] = query
        st.session_state["search_location"] = location.strip() or "India"
        api_key = get_secret("SERPAPI_API_KEY")
        if not api_key:
            st.session_state["search_error"] = (
                "Live API search needs a SerpAPI key. Until it is configured, use "
                "the Google Jobs link below; the AI career guidance still works."
            )
            st.session_state.pop("jobs", None)
        else:
            try:
                st.session_state["jobs"] = search_google_jobs(
                    query=query, location=location, api_key=api_key
                )
                st.session_state.pop("search_error", None)
                st.session_state["search_query"] = query
            except JobSearchError as exc:
                st.session_state["search_error"] = str(exc)
                st.session_state.pop("jobs", None)

if st.session_state.get("search_error"):
    previous_generic_error = "Could not reach the job search provider. Check your network connection."
    if st.session_state["search_error"] == previous_generic_error:
        st.session_state["search_error"] = (
            "This is an old, generic error from before provider diagnostics were added. "
            "Select “Find jobs” again to see whether the current issue is the API key, quota, "
            "network, or provider. Google Jobs is also available through the link below."
        )
    st.warning(st.session_state["search_error"])

jobs = st.session_state.get("jobs", [])
resume_text = ""
if uploaded_resume is not None:
    try:
        resume_text = extract_resume_text(uploaded_resume.name, uploaded_resume.getvalue())
        if not resume_text.strip():
            st.warning("No readable text was found. If this is a scanned PDF, use an OCR-enabled PDF.")
    except ResumeParseError as exc:
        st.error(str(exc))

if resume_text and not jobs:
    st.info(
        "Your resume was read successfully. Enter a role and select **Find jobs** to "
        "compare it with live listings and see match scores."
    )

search_query = st.session_state.get("search_query", "")
search_location = st.session_state.get("search_location", location.strip() or "India")
left, right = st.columns([2, 1], gap="large")

with left:
    st.markdown('<div id="matches"></div>', unsafe_allow_html=True)
    st.subheader("Job matches")
    if jobs:
        st.caption(f"{len(jobs)} Google Jobs results for “{search_query}”")
        for job in jobs:
            score = match_score(resume_text, job) if resume_text else None
            with st.container(border=True):
                heading, badge = st.columns([4, 1])
                with heading:
                    st.markdown(f"### {job['title']}")
                    st.write(f"**{job['company']}** · {job['location']}")
                with badge:
                    if score is not None:
                        st.metric("Resume match", f"{score}%")
                if job.get("via"):
                    st.caption(f"Listed {job['via']}")
                if job.get("posted_at"):
                    st.caption(f"Posted {job['posted_at']}")
                if job.get("salary"):
                    st.caption(f"Salary: {job['salary']}")
                if job.get("description"):
                    description = job["description"]
                    st.write(description[:700] + ("…" if len(description) > 700 else ""))
                links = job.get("apply_links", [])
                if links:
                    company_link = next(
                        (
                            link
                            for link in links
                            if re.search(
                                r"\b(?:company|employer|careers?)\b",
                                link.get("title", ""),
                                re.IGNORECASE,
                            )
                        ),
                        None,
                    )
                    primary_link = company_link or links[0]
                    action_label = (
                        "Apply on company site"
                        if company_link
                        else "View job / apply"
                    )
                    st.link_button(action_label, primary_link["link"])
                    remaining_links = [
                        link for link in links if link is not primary_link
                    ]
                    if remaining_links:
                        with st.expander("More application links"):
                            for option in remaining_links:
                                st.link_button(option["title"], option["link"])
    else:
        if search_query:
            provider_query = re.sub(
                r"\s+jobs?\s*$", "", search_query, flags=re.IGNORECASE
            )
            browser_jobs_url = (
                "https://www.google.com/search?q="
                + quote_plus(f"{provider_query} jobs {search_location}")
            )
            st.markdown(
                """
                <div style="padding:1rem 1.1rem;border:1px solid #d9d4ff;border-radius:15px;
                background:linear-gradient(110deg,#f2efff,#edf8ff);color:#27304b">
                <strong>Live job results are still one click away</strong><br>
                SerpAPI is not configured or unavailable. Open Google Jobs search directly;
                this app does not invent job listings.
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button(
                "🌐  Open live job search",
                browser_jobs_url,
                use_container_width=True,
            )
        else:
            st.info("Enter a role, company, or domain above to explore matching opportunities.")

with right:
    st.markdown('<div id="assistant"></div>', unsafe_allow_html=True)
    st.subheader("AI career assistant")
    st.caption("Ask a question about jobs, skills, resumes, interviews, or your career plan.")
    if st.session_state.get("assistant_chat_version") != "question-answer-v1":
        st.session_state["assistant_chat"] = []
        st.session_state["assistant_chat_version"] = "question-answer-v1"
        st.session_state.pop("assistant_chat_notice", None)
    st.session_state.setdefault("assistant_chat", [])
    clear_col, status_col = st.columns([1, 2], vertical_alignment="center")
    with clear_col:
        if st.button("🗑️ Clear chat", key="clear_assistant_chat", use_container_width=True):
            st.session_state["assistant_chat"] = []
            st.session_state.pop("assistant_chat_notice", None)
            st.rerun()
    with status_col:
        if get_secret("GEMINI_API_KEY"):
            st.caption("Gemini AI is enabled · responses can use current job results")
        else:
            st.caption(
                "Local career guidance is active · configure Gemini for open-ended AI responses"
            )

    with st.container(height=360, border=True):
        if not st.session_state["assistant_chat"]:
            st.info(
                "Hello! Ask a question about your job search, skills, resume, or interview preparation. "
                "For example: “I have two years of experience. What skills should I build for a GenAI role?”"
            )
        for message in st.session_state["assistant_chat"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    chat_prompt = st.chat_input(
        "Ask your career question…",
        key="assistant_chat_input",
        max_chars=1000,
    )
    if chat_prompt:
        previous_messages = list(st.session_state["assistant_chat"])
        st.session_state["assistant_chat"].append(
            {"role": "user", "content": chat_prompt}
        )
        chat_jobs = jobs
        chat_search_query = search_query
        chat_location = search_location
        provider_notice = ""
        requested_search = extract_job_search_request(chat_prompt, search_location)
        if requested_search:
            chat_jobs = []
            requested_role, chat_search_query, chat_location = requested_search
            st.session_state["search_query"] = chat_search_query
            st.session_state["search_location"] = chat_location
            st.session_state.pop("jobs", None)
            api_key = get_secret("SERPAPI_API_KEY")
            if api_key:
                try:
                    fallback_query = (
                        "Production Support Engineer jobs"
                        if requested_role.casefold() == "production support"
                        else f"{requested_role} jobs"
                    )
                    chat_jobs, fallback_notice = search_google_jobs_with_fallback(
                        query=chat_search_query,
                        fallback_query=fallback_query,
                        location=chat_location,
                        api_key=api_key,
                    )
                    provider_result_count = len(chat_jobs)
                    chat_jobs = filter_jobs_for_role(requested_role, chat_jobs)
                    if provider_result_count and not chat_jobs:
                        fallback_notice = (
                            "The provider returned listings, but none had a title matching "
                            "the requested role. No unrelated listings are shown."
                        )
                    provider_notice = fallback_notice
                    st.session_state["jobs"] = chat_jobs
                    st.session_state["search_query"] = chat_search_query
                    st.session_state["search_location"] = chat_location
                    st.session_state.pop("search_error", None)
                except JobSearchError as exc:
                    provider_notice = f"Live job lookup failed: {exc}"
            else:
                provider_notice = (
                    "Live job lookup requires a valid SERPAPI_API_KEY. "
                    "A direct Google Jobs search link is included in the response."
                )
        if requested_search:
            answer = local_career_answer(
                question=chat_prompt,
                jobs=chat_jobs,
                search_query=chat_search_query,
                location=chat_location,
            )
            notice = provider_notice
        else:
            try:
                answer = answer_career_question(
                    question=chat_prompt,
                    jobs=chat_jobs,
                    search_query=chat_search_query,
                    history=previous_messages,
                    gemini_api_key=get_secret("GEMINI_API_KEY"),
                    resume_text=resume_text,
                    send_resume_to_gemini=use_resume_with_gemini,
                    location=chat_location,
                )
                notice = provider_notice
            except SuggestionError as exc:
                notice = (
                    f"Gemini is temporarily unavailable; showing local career guidance. {exc}"
                )
                if provider_notice:
                    notice = f"{notice} {provider_notice}"
                answer = local_career_answer(
                    question=chat_prompt,
                    jobs=chat_jobs,
                    search_query=chat_search_query,
                    location=chat_location,
                )
        if notice:
            st.session_state["assistant_chat_notice"] = notice
        else:
            st.session_state.pop("assistant_chat_notice", None)
        st.session_state["assistant_chat"].append(
            {"role": "assistant", "content": answer}
        )
        st.rerun()

    if st.session_state.get("assistant_chat_notice"):
        st.warning(st.session_state["assistant_chat_notice"])

    if jobs or search_query:
        with st.expander("Quick suggestions from your search"):
            for suggestion in generate_suggestions(
                query=search_query,
                jobs=jobs,
                resume_text=resume_text,
            ):
                st.markdown(f"- {suggestion}")

    st.divider()
    st.markdown('<div id="job-boards"></div>', unsafe_allow_html=True)
    st.subheader("Explore other job boards")
    search_terms = " ".join(part for part in (role, company, location) if part)
    if search_terms:
        encoded = quote_plus(search_terms)
        glassdoor_url = f"https://www.google.com/search?q=site%3Aglassdoor.com%2FJob%2F+{encoded}"
        internshala_url = f"https://www.google.com/search?q=site%3Ainternshala.com%2Fjobs%2F+{encoded}"
        st.link_button("Search Glassdoor listings", glassdoor_url, use_container_width=True)
        st.link_button("Search Internshala listings", internshala_url, use_container_width=True)
        st.caption("These links open web search results; direct partner API access is not configured.")

    if jobs:
        companies = sorted({job["company"] for job in jobs if job.get("company")})
        if companies:
            st.divider()
            st.subheader("Company career pages")
            for name in companies[:5]:
                careers_url = (
                    "https://www.google.com/search?q="
                    + quote_plus(f"{name} official careers")
                )
                st.link_button(f"{name} · find official careers", careers_url, use_container_width=True)
            st.caption("Search results help locate each company’s official careers page.")

with st.expander("Data sources and setup notes"):
    st.markdown(
        """
        - **Google Jobs:** fetched through SerpAPI's Google Jobs engine. This is a third-party
          provider, not a public Google Jobs API. Results and quotas depend on your SerpAPI plan.
        - **Glassdoor / Internshala:** this MVP does not claim direct API access. Their links
          open searches for listings; integrate direct data only with approved partner access.
        - **Resume matching:** local keyword overlap score, not a hiring decision or guarantee.
          PDF/DOCX text is processed in memory and not persisted by this app.
        - **Gemini:** optional. Resume text is only sent to Gemini when `GEMINI_API_KEY` is
          configured and a resume is uploaded; otherwise suggestions are generated locally.
        """
    )

st.markdown(
    """
    <footer class="app-footer">
      <strong>Career Compass AI</strong> · Built to make your next career move clearer.<br>
      Job listings depend on their providers. Always confirm job details on the employer’s
      official careers page. <a href="#search">Back to search ↑</a>
    </footer>
    """,
    unsafe_allow_html=True,
)
