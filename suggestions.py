import re
from typing import Any
from urllib.parse import quote_plus

import requests


GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_FALLBACK_MODELS = ("gemini-3.5-flash",)


class SuggestionError(Exception):
    """Raised when the optional Gemini suggestion request fails."""


def is_career_preparation_question(question: str) -> bool:
    normalized = question.casefold()
    return bool(
        re.search(r"\b(?:prepar(?:e|ing|ation)|prep)\b", normalized)
        and not re.search(
            r"\b(?:find|search|looking for|current|latest)\b",
            normalized,
        )
    )


def _extract_role_request(question: str) -> tuple[str, str] | None:
    normalized = question.lower()
    fresher = re.search(
        r"\b(?:for\s+)?(?:freshers?|entry[- ]level|graduates?)\b",
        normalized,
    )
    if fresher:
        preparation_intent = re.search(
            r"\b(?:prepar(?:e|ing|ation)|prep)\b",
            normalized[:fresher.start()],
        )
        leading_search_intent = re.fullmatch(
            r"\s*(?:(?:i\s+)?(?:looking\s+for|search(?:ing)?\s+for|find\s+me|"
            r"apply\s+for|target(?:ing)?|want|wan|need|find)\s+)?",
            normalized[:fresher.start()],
        )
        if preparation_intent or leading_search_intent:
            role_text = normalized[fresher.end():]
            role_text = re.sub(r"^\s*(?:for|to|as|in)\s+", "", role_text)
        else:
            role_text = normalized[:fresher.start()]
            role_text = re.sub(
                r"^\s*(?:(?:i\s+)?(?:looking\s+for|search(?:ing)?\s+for|find\s+me|"
                r"apply\s+for|target(?:ing)?|want|wan|need|find)\s+|"
                r"(?:i\s+)?(?:am|work(?:ing)?\s+as)\s+)",
                "",
                role_text,
            )
        role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
        role_text = re.sub(r"\b(?:jobs?|roles?|positions?)\s*$", "", role_text).strip()
        role_text = re.sub(r"\bdevloper\b", "developer", role_text)
        role_text = re.sub(r"\bdev\b", "developer", role_text)
        role_text = re.sub(r"\beng\b", "engineer", role_text)
        role_text = re.sub(r"^\s*(?:job\s+)?role\s+(?:in|for|as)\s+", "", role_text)
        role_text = re.sub(r"\b(?:job\s+)?role\s*$", "", role_text).strip()
        role_text = re.sub(r"\s+", " ", role_text).strip()
        if not role_text or len(role_text) > 80:
            return None
        if re.fullmatch(r"intern(?:ship)?", role_text):
            return "Internship", "internship"
        return _format_role_title(role_text), "fresher / entry-level"

    experience = re.search(
        r"\b(\d+)\s*(?:\+)?\s*(?:(?:-|–|—|to|\.{2,3})\s*(\d+)\s*)?"
        r"(years?|yrs?|yr|experience|exp)\b",
        normalized,
    )
    if not experience:
        return None

    role_prefix = normalized[:experience.start()]
    describes_own_experience = bool(re.match(r"^\s*i\s+have\b", role_prefix))
    role_text = role_prefix
    role_text = re.sub(
        r"^\s*(?:(?:i\s+)?(?:looking\s+for|search(?:ing)?\s+for|find\s+me|"
        r"apply\s+for|target(?:ing)?|want|need|find)\s+|"
        r"(?:i\s+)?(?:am|work(?:ing)?\s+as)\s+)",
        "",
        role_text,
    )
    if describes_own_experience:
        role_text = ""
    role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
    role_text = re.sub(r"\b(?:with|having|and)\s*$", "", role_text).strip()
    role_text = re.sub(r"\b(?:jobs?|roles?|positions?)\s*$", "", role_text).strip()
    role_text = re.sub(r"\bdev\b", "developer", role_text)
    role_text = re.sub(r"\bdevloper\b", "developer", role_text)
    role_text = re.sub(r"\beng\b", "engineer", role_text)
    role_text = re.sub(r"^\s*(?:job\s+)?role\s+(?:in|for|as)\s+", "", role_text)
    role_text = re.sub(r"\b(?:job\s+)?role\s*$", "", role_text).strip()
    role_text = re.sub(r"\s+", " ", role_text)
    if not role_text and not describes_own_experience:
        role_text = re.sub(
            r"^\s*(?:(?:of\s+)?(?:experience|exp)\s*)?(?:in|as|for)\s+",
            "",
            normalized[experience.end():],
        )
        role_text = re.sub(r"^\s*(?:experience|exp)\s+", "", role_text)
        role_text = re.split(r"[,?.!]", role_text, maxsplit=1)[0].strip()
        role_text = re.sub(r"\b(?:job|role|position)\s*$", "", role_text).strip()
        role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
        role_text = re.sub(r"\bdev\b", "developer", role_text)
        role_text = re.sub(r"\bdevloper\b", "developer", role_text)
        role_text = re.sub(r"\beng\b", "engineer", role_text)
        role_text = re.sub(r"^\s*(?:job\s+)?role\s+(?:in|for|as)\s+", "", role_text)
        role_text = re.sub(r"\b(?:job\s+)?role\s*$", "", role_text).strip()
    if not role_text or len(role_text) > 80:
        return None

    if experience.group(2):
        experience_text = (
            f"{experience.group(1)}-{experience.group(2)} years of experience"
        )
    else:
        plus = "+" if re.search(r"\d+\s*\+", experience.group(0)) else ""
        unit = "year" if experience.group(1) == "1" and not plus else "years"
        experience_text = f"{experience.group(1)}{plus} {unit} of experience"
    return _format_role_title(role_text), experience_text


def _format_role_title(role_text: str) -> str:
    role_text = role_text.replace("\u2011", "-")
    role_text = re.sub(r"\bfront[- ]end\b", "frontend", role_text, flags=re.IGNORECASE)
    role_text = re.sub(r"\bback[- ]end\b", "backend", role_text, flags=re.IGNORECASE)
    role_text = re.sub(r"\bfull\s+stack\b", "full-stack", role_text, flags=re.IGNORECASE)
    role_title = role_text.title()
    role_title = re.sub(r"\bSql\b", "SQL", role_title)
    role_title = re.sub(r"\bPl/Sql\b", "PL/SQL", role_title)
    role_title = re.sub(r"\bGen Ai\b", "GenAI", role_title)
    role_title = re.sub(r"\bLlm\b", "LLM", role_title)
    role_title = re.sub(r"\bIt\b", "IT", role_title)
    role_title = re.sub(r"\bAi\b", "AI", role_title)
    role_title = re.sub(r"\bQa\b", "QA", role_title)
    role_title = re.sub(r"\bSre\b", "SRE", role_title)
    role_title = re.sub(r"\bDevops\b", "DevOps", role_title)
    role_title = re.sub(r"\bUi/Ux\b", "UI/UX", role_title)
    role_title = re.sub(r"\bIos\b", "iOS", role_title)
    if role_title == "Java":
        role_title = "Java Developer"
    if role_title == "Frontend":
        role_title = "Frontend Developer"
    if role_title == "Backend":
        role_title = "Backend Developer"
    if role_title in ("GenAI", "Generative AI"):
        role_title = "GenAI Developer"
    return role_title


def extract_job_search_request(
    question: str,
    default_location: str = "India",
) -> tuple[str, str, str] | None:
    """Return (role, provider query, location) for an explicit job-search request."""
    normalized = re.sub(r"\bintership\b", "internship", question.lower())
    if is_career_preparation_question(normalized):
        return None
    location_match = re.search(
        r"\b(?:in|near|around)\s+([a-z][a-z .'-]{1,45})\s*[?.!]*$",
        normalized,
    )
    if location_match and re.search(
        r"^(?:front[- ]end|back[- ]end|frontend|backend|full[- ]stack)\s+(?:job\s+)?roles?$",
        location_match.group(1).strip(),
    ):
        location_match = None
    requested_location = (
        re.sub(r"\s+", " ", location_match.group(1)).strip(" .-'").title()
        if location_match
        else default_location.strip() or "India"
    )
    if location_match:
        normalized = normalized[:location_match.start()].strip()

    role_request = _extract_role_request(normalized)
    salary_match = re.search(
        r"\b(above|over|more than|at least|minimum|min\.?)?\s*"
        r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(lpa|lakhs?|lakh per annum|per annum)\b",
        normalized,
    )
    salary_text = ""
    if salary_match:
        comparison = (salary_match.group(1) or "").lower()
        amount = salary_match.group(2)
        salary_text = f"{comparison or 'at least'} {amount} LPA" if comparison else f"{amount} LPA"
        normalized = normalized[:salary_match.start()] + normalized[salary_match.end():]
        role_request = _extract_role_request(normalized)

    if role_request:
        role, experience = role_request
        provider_role = "Application Production Support Engineer" if role.casefold() == "production support" else role
        query_terms = [provider_role]
        if experience == "fresher / entry-level":
            query_terms.append("fresher")
        elif experience == "internship":
            if role.casefold() != "internship":
                query_terms.append("internship")
        else:
            query_terms.append(experience.replace(" of experience", " experience"))
        if salary_text:
            query_terms.append(salary_text)
        return role, f"{' '.join(query_terms)} jobs", requested_location

    internship = re.search(r"\bintern(?:ship)?\b", normalized)
    if internship:
        role_text = normalized[:internship.start()] + normalized[internship.end():]
        role_text = re.sub(
            r"^\s*(?:(?:i\s+)?(?:want|need|looking\s+for|search(?:ing)?\s+for|"
            r"find(?:\s+me)?|show\s+me)\s+)+",
            "",
            role_text,
        )
        role_text = re.sub(r"\b(?:job\s+)?role\s*$", "", role_text).strip()
        role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
        role_text = re.sub(r"\bdevloper\b", "developer", role_text)
        role_text = re.sub(r"\bdev\b", "developer", role_text)
        role_text = re.sub(r"\beng\b", "engineer", role_text)
        role = _format_role_title(role_text) if role_text else "Internship"
        query_terms = [role]
        if role.casefold() != "internship":
            query_terms.append("internship")
        if salary_text:
            query_terms.append(salary_text)
        return role, f"{' '.join(query_terms)} jobs", requested_location

    if salary_text:
        role_text = re.sub(
            r"^\s*(?:(?:i\s+)?(?:want|need|looking\s+for|search(?:ing)?\s+for|"
            r"find(?:\s+me)?|show\s+me)\s+)+",
            "",
            normalized,
        )
        role_text = re.sub(r"\b(?:job\s+)?role\s*$", "", role_text).strip()
        role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
        role_text = re.sub(r"\bdev\b", "developer", role_text)
        if role_text:
            role = _format_role_title(role_text)
            return role, f"{role} jobs {salary_text}", requested_location

    explicit_role_only_request = bool(
        re.match(
            r"^\s*(?:(?:i\s+)?(?:want|need)\s+).+\b"
            r"(?:jobs?|roles?|positions?|internships?)\b",
            normalized,
        )
    )
    search_intent = explicit_role_only_request or any(
        term in normalized
        for term in (
            "current",
            "latest",
            "job",
            "opening",
            "vacanc",
            "find me",
            "looking for",
        )
    )
    if not search_intent or re.match(r"^\s*(?:which|what|how|where|when)\b", normalized):
        return None

    role_text = re.sub(
        r"^\s*(?:(?:i\s+)?(?:want|need|looking\s+for|search(?:ing)?\s+for|"
        r"find(?:\s+me)?|show\s+me|wan)\s+)+",
        "",
        normalized,
    )
    role_text = re.sub(r"\b(?:current|latest|available|open)\b", "", role_text)
    role_text = re.sub(
        r"\b(?:jobs?|roles?|openings?|vacancies|positions?)\s*$", "", role_text
    )
    role_text = re.sub(r"^\s*(?:a|an|the)\s+", "", role_text)
    role_text = re.sub(r"\bdevloper\b", "developer", role_text)
    role_text = re.sub(r"\bdev\b", "developer", role_text)
    role_text = re.sub(r"\beng\b", "engineer", role_text)
    role_text = re.sub(r"\s+", " ", role_text).strip(" .-'")
    if not role_text or len(role_text) > 80:
        return None

    role = _format_role_title(role_text)
    return role, f"{role} jobs", requested_location


def _matching_jobs_for_role(
    role: str,
    jobs: list[dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    normalized_role = role.lower()
    if "internship" in normalized_role or re.search(r"\bintern\b", normalized_role):
        base_role = re.sub(r"\b(?:internship|intern)\b", "", normalized_role)
        base_terms = set(re.findall(r"[a-z0-9+#]+", base_role))
        base_terms -= {"developer", "engineer", "programmer", "job", "role", "with", "and", "in", "for"}
        return [
            job
            for job in jobs
            if re.search(
                r"\bintern(?:ship)?\b",
                str(job.get("title", "")).lower(),
            )
            and base_terms.issubset(
                set(re.findall(r"[a-z0-9+#]+", str(job.get("title", "")).lower()))
            )
        ][:limit]
    if any(term in normalized_role for term in ("genai", "generative ai", "llm", "rag")):
        generative_ai_terms = ("genai", "gen ai", "generative ai", "llm", "rag")
        return [
            job
            for job in jobs
            if any(
                term in f"{job.get('title', '')} {job.get('description', '')}".lower()
                for term in generative_ai_terms
            )
        ][:limit]

    role_terms = set(re.findall(r"[a-z0-9+#]+", role.lower()))
    title_normalization = {
        "front-end": "frontend",
        "front end": "frontend",
        "back-end": "backend",
        "back end": "backend",
    }
    family_terms = {
        "developer": {"developer", "engineer", "programmer"},
        "engineer": {"engineer", "developer", "programmer"},
        "specialist": {"specialist"},
        "analyst": {"analyst"},
        "consultant": {"consultant"},
        "administrator": {"administrator", "admin"},
        "architect": {"architect"},
        "manager": {"manager"},
        "designer": {"designer"},
        "support": {"support"},
        "scientist": {"scientist"},
        "tester": {"tester", "qa"},
    }
    ignored_terms = {"job", "role", "with", "and", "in", "for"}
    specific_terms = role_terms - set(family_terms) - ignored_terms
    if not specific_terms:
        specific_terms = role_terms

    def title_matches(job: dict[str, Any]) -> bool:
        normalized_title = str(job.get("title", "")).lower()
        for source, replacement in title_normalization.items():
            normalized_title = normalized_title.replace(source, replacement)
        title_terms = set(
            re.findall(r"[a-z0-9+#]+", normalized_title)
        )
        required_families = role_terms & family_terms.keys()
        return specific_terms.issubset(title_terms) and all(
            title_terms & family_terms[family] for family in required_families
        )

    return [
        job
        for job in jobs
        if title_matches(job)
    ][:limit]


def _matching_jobs_for_search(
    role: str,
    jobs: list[dict[str, Any]],
    search_query: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if re.search(r"\bintern(?:ship)?\b", search_query, re.IGNORECASE):
        role = f"{role} Internship"
    return _matching_jobs_for_role(role, jobs, limit)


def filter_jobs_for_role(
    role: str,
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep provider listings whose titles match the requested role."""
    return _matching_jobs_for_role(role, jobs, limit=10)


def _asks_for_company_names(question: str) -> bool:
    normalized = question.lower()
    return bool(
        re.search(
            r"\b(?:company|companies|employer|employers)\b",
            normalized,
        )
    )


def _asks_for_skill_development(question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:improv\w*|build|learn|upskill\w*|strengthen\w*)\b"
            r"|\bdevelop(?:ing)?\s+(?:(?:my|your|these|the)\s+)?skills?\b"
            r"|\bskills?\b",
            question,
            re.IGNORECASE,
        )
    )


def _role_from_search_query(search_query: str) -> str | None:
    normalized = search_query.lower()
    if "production support" in normalized:
        return "Production Support"
    role_request = _extract_role_request(search_query)
    return role_request[0] if role_request else None


def local_career_answer(
    question: str,
    jobs: list[dict[str, Any]],
    search_query: str = "",
    location: str = "India",
) -> str:
    normalized = question.lower()
    relevant_jobs = jobs[:4]
    job_list = "\n".join(
        f"- **{job.get('title', 'Role')}** at {job.get('company', 'Company')} "
        f"({job.get('location', 'Location not listed')})"
        for job in relevant_jobs
    )

    if _asks_for_company_names(question):
        role = _role_from_search_query(search_query)
        company_jobs = (
            _matching_jobs_for_search(role, jobs, search_query) if role else jobs
        )
        if not company_jobs:
            company_jobs = jobs
        companies: dict[str, list[str]] = {}
        for job in company_jobs:
            company = str(job.get("company", "")).strip()
            if company and company != "Company not listed":
                title = str(job.get("title", "Role")).strip()
                companies.setdefault(company, [])
                if title and title not in companies[company]:
                    companies[company].append(title)
        if companies:
            company_list = "\n".join(
                f"- **{company}** — {', '.join(titles[:2])}"
                for company, titles in list(companies.items())[:8]
            )
            return (
                "These companies appear in the current job-search results:\n"
                f"{company_list}\n\n"
                "Open each listing to confirm it is active and check its experience "
                "requirements before applying."
            )
        return (
            "I don’t have company names in the current job results. Run the role search "
            "again to load live listings, and I can list the companies shown there."
        )

    if re.search(r"\b(?:prepar(?:e|ing|ation)|prep)\b", normalized):
        preparation_request = _extract_role_request(question)
        if preparation_request and preparation_request[1] == "fresher / entry-level":
            target_role = preparation_request[0]
            if "java" in target_role.casefold():
                preparation_steps = (
                    "1. Review Java fundamentals, object-oriented programming, collections, "
                    "exceptions, and basic streams.\n"
                    "2. Practise SQL, REST API basics, Git, and unit testing.\n"
                    "3. Build a small Java project, such as a REST API with a database, and "
                    "be ready to explain your design and tests.\n"
                    "4. Practise coding problems and clear explanations of your project."
                )
            else:
                preparation_steps = (
                    "1. Review the role's core programming language and fundamentals.\n"
                    "2. Practise data structures, SQL, Git, testing, and basic API concepts "
                    "where relevant.\n"
                    "3. Build a small project using the target role's tools and be ready to "
                    "explain your design and tests.\n"
                    "4. Practise coding problems and concise project explanations."
                )
            return (
                f"To prepare for a fresher **{target_role}** role:\n"
                f"{preparation_steps}\n"
                "Use entry-level job descriptions to prioritise topics; I don't have a "
                "specific vacancy from this preparation question."
            )

    is_snowflake_request = "snowflake" in normalized
    if is_snowflake_request:
        experience = re.search(
            r"\b(\d+)\s*(?:-\s*(\d+)\s*)?(?:years?|yrs?)\.?\b",
            normalized,
        )
        experience_text = (
            f"{experience.group(1)} years of experience"
            if experience
            else "your experience level"
        )
        if _asks_for_skill_development(question):
            experience_label = (
                f"With {experience_text}, prioritize the areas that are weakest in your "
                "current projects; don't assume you need to learn everything from scratch."
            )
            return (
                f"{experience_label}\n\n"
                "1. **Performance and cost:** read Query Profiles, identify pruning and "
                "spilling issues, and tune warehouse size and query patterns.\n"
                "2. **Reliable ELT:** practise Streams and Tasks, Snowpipe, incremental "
                "loads, and recovery from failed or duplicate loads.\n"
                "3. **Data modelling and transformation:** strengthen dimensional modelling, "
                "SCD patterns, dbt, and automated data-quality tests.\n"
                "4. **Platform and security:** build confidence with RBAC, masking and row "
                "access policies, secure data sharing, and environment promotion.\n"
                "5. **Engineering practice:** use Git and CI/CD, monitoring, documentation, "
                "and Python/Snowpark when the target roles require them.\n\n"
                "Choose two gaps that appear repeatedly in Snowflake Developer job "
                "descriptions, then demonstrate them in a small end-to-end project with "
                "measured performance or reliability improvements."
            )
        matching_jobs = [
            job
            for job in jobs
            if "snowflake"
            in f"{job.get('title', '')} {job.get('description', '')}".lower()
        ][:4]
        answer = (
            f"With {experience_text}, target **Snowflake Developer**, **Snowflake Data Engineer**, "
            "and **Cloud Data Warehouse Developer** roles. Highlight Snowflake SQL, data modelling, "
            "ETL/ELT, warehouses, stages, and performance/cost optimisation when these match your "
            "hands-on experience. Streams, tasks, Snowpipe, and dbt are useful additions where "
            "they appear in the job requirements."
        )
        if matching_jobs:
            matching_list = "\n".join(
                f"- **{job.get('title', 'Snowflake role')}** at "
                f"{job.get('company', 'Company')} "
                f"({job.get('location', 'Location not listed')})"
                for job in matching_jobs
            )
            return (
                f"{answer}\n\n**Matching roles in the current results:**\n{matching_list}\n\n"
                "Open each listing to confirm its experience requirements before applying."
            )

        query_terms = ["Snowflake Developer"]
        if experience:
            query_terms.append(f"{experience.group(1)} years experience")
        query_terms.extend(["jobs", location or "India"])
        jobs_url = "https://www.google.com/search?q=" + quote_plus(" ".join(query_terms))
        return (
            f"{answer}\n\nNo matching Snowflake openings are loaded in this search yet. "
            f"[Search Snowflake Developer jobs for {experience_text} in {location or 'India'}]"
            f"({jobs_url}). You can also enter **Snowflake Developer** in the search form "
            "above to load matching results."
        )

    is_oracle_request = any(
        term in normalized for term in ("oracle", "pl/sql", "pl sql", "plsql")
    )
    if is_oracle_request:
        experience = re.search(
            r"\b(\d+)\s*(?:-\s*(\d+)\s*)?(?:years?|yrs?)\.?\b",
            normalized,
        )
        experience_text = (
            f"{experience.group(1)} years of experience"
            if experience
            else "your experience level"
        )
        matching_jobs = [
            job
            for job in jobs
            if any(
                term in f"{job.get('title', '')} {job.get('description', '')}".lower()
                for term in ("oracle", "pl/sql", "pl sql", "plsql")
            )
        ][:4]
        answer = (
            f"With {experience_text}, target **Oracle Developer**, **PL/SQL Developer**, "
            "and **Oracle Database Developer** roles. Emphasize Oracle SQL and PL/SQL, "
            "stored procedures, packages, triggers, query tuning, and database performance "
            "where these reflect your actual experience."
        )
        if matching_jobs:
            matching_list = "\n".join(
                f"- **{job.get('title', 'Oracle role')}** at "
                f"{job.get('company', 'Company')} "
                f"({job.get('location', 'Location not listed')})"
                for job in matching_jobs
            )
            return (
                f"{answer}\n\n**Matching roles in the current results:**\n{matching_list}\n\n"
                "Open each listing to confirm its experience requirements before applying."
            )

        query_terms = ["Oracle Developer"]
        if experience:
            query_terms.append(f"{experience.group(1)} years experience")
        query_terms.extend(["jobs", location or "India"])
        jobs_url = "https://www.google.com/search?q=" + quote_plus(" ".join(query_terms))
        return (
            f"{answer}\n\nNo matching Oracle openings are loaded in this search yet. "
            f"[Search Oracle Developer jobs for {experience_text} in {location or 'India'}]({jobs_url}). "
            "You can also enter **Oracle Developer** in the search form above to load matching results."
        )

    role_request = _extract_role_request(question)
    if role_request:
        target_role, experience_text = role_request
        matching_jobs = _matching_jobs_for_search(target_role, jobs, search_query)
        lower_role = target_role.lower()
        if any(term in lower_role for term in ("genai", "generative ai", "llm", "rag")):
            skills = (
                "Build a portfolio around Python, LLM APIs, prompt design, embeddings, and RAG. "
                "Create and deploy one small project that answers questions from cited documents; "
                "be ready to explain how you tested answer quality."
            )
        elif "sql" in lower_role and "developer" in lower_role:
            skills = (
                "Emphasize SQL query writing and optimisation, joins, stored procedures, "
                "database design, and query performance where these reflect your experience."
            )
        elif "python" in lower_role and "developer" in lower_role:
            skills = (
                "Highlight Python, APIs, testing, debugging, and the projects or services "
                "you have delivered."
            )
        elif "data analyst" in lower_role:
            skills = (
                "Highlight SQL, data cleaning, reporting, dashboards, and examples where "
                "your analysis informed a decision."
            )
        elif "frontend" in lower_role:
            skills = (
                "Emphasize the frontend frameworks, JavaScript or TypeScript, responsive "
                "design, accessibility, testing, and measurable product outcomes you have "
                "actually worked with."
            )
        else:
            skills = (
                "Tailor your resume to the tools and skills listed in relevant job descriptions, "
                "and include measurable outcomes from your work."
            )
        if experience_text == "fresher / entry-level":
            answer = (
                f"As a fresher, target **{target_role}**, **LLM Application Developer**, "
                "and **GenAI Engineer Intern** roles that welcome entry-level applicants. "
                f"{skills}"
            )
        else:
            answer = (
                f"With {experience_text}, target **{target_role}** roles that ask for a similar "
                "level of experience. Requirements vary by employer, so check each posting carefully. "
                f"{skills}"
            )
        if matching_jobs:
            matching_list = "\n".join(
                f"- **{job.get('title', target_role)}** at "
                f"{job.get('company', 'Company')} "
                f"({job.get('location', 'Location not listed')})"
                for job in matching_jobs
            )
            return (
                f"{answer}\n\n**Potential matches in the current results:**\n"
                f"{matching_list}\n\nOpen each listing to confirm its experience "
                "requirements before applying."
            )

        experience_query = (
            "fresher" if experience_text == "fresher / entry-level" else experience_text
        )
        query = f"{target_role} {experience_query} jobs {location or 'India'}"
        jobs_url = "https://www.google.com/search?q=" + quote_plus(query)
        return (
            f"{answer}\n\nNo matching roles are loaded in the current results. "
            f"[Search {target_role} jobs for {experience_text} in {location or 'India'}]"
            f"({jobs_url}). You can also enter **{target_role}** in the search form "
            "to fetch matching listings."
        )

    current_search = extract_job_search_request(question, location)
    if current_search:
        target_role, query, requested_location = current_search
        matching_jobs = _matching_jobs_for_search(target_role, jobs, query)
        if matching_jobs:
            matching_list = "\n".join(
                f"- **{job.get('title', target_role)}** at "
                f"{job.get('company', 'Company')} "
                f"({job.get('location', 'Location not listed')})"
                for job in matching_jobs
            )
            return (
                f"Here are current **{target_role}** results for **{requested_location}**:\n"
                f"{matching_list}\n\nOpen each listing to verify the posting date, "
                "experience requirements, and application details."
            )
        jobs_url = "https://www.google.com/search?q=" + quote_plus(
            f"{query} {requested_location}"
        )
        return (
            f"You're looking for current **{target_role}** roles in **{requested_location}**. "
            "I couldn't load verified live listings into this session, so I won't invent "
            "openings. "
            f"[Search {target_role} jobs in {requested_location}]({jobs_url})."
        )

    if any(term in normalized for term in ("resume", "résumé", "cv", "curriculum")):
        if "java" in normalized or "java" in search_query.lower():
            return (
                "Build your Java Developer resume in this order:\n"
                "1. **Summary:** 2–3 lines on your Java experience, strongest backend skills, "
                "and the kind of role you want.\n"
                "2. **Technical skills:** list only skills you can discuss, such as Core Java, "
                "collections, Spring Boot, REST APIs, SQL, Git, and testing.\n"
                "3. **Experience and projects:** for each item, state what you built, the "
                "technology used, and a measurable result. Mention API, database, or "
                "performance improvements when accurate.\n"
                "4. **Education and links:** add relevant education, certifications, GitHub, "
                "and a clean LinkedIn URL.\n\n"
                "Keep it easy to scan, tailor keywords to each job description, and do not "
                "claim tools or results you cannot explain."
            )
        return (
            "To improve your resume for this search:\n"
            "1. Put your target role and strongest matching skills near the top.\n"
            "2. Describe projects with action + technology + measurable result.\n"
            "3. Mirror relevant skills from the job description, but only if you genuinely have them.\n"
            "4. Keep formatting simple and check dates, spelling, and contact links."
            + (f"\n\nCurrent target: **{search_query}**." if search_query else "")
        )
    if any(term in normalized for term in ("interview", "prepare", "preparation")):
        return (
            "A practical interview-prep plan:\n"
            "1. Prepare a 60-second introduction linked to the role.\n"
            "2. Practise explaining two projects, your decisions, and measurable outcomes.\n"
            "3. Review the skills named in the role and solve a few realistic problems.\n"
            "4. Prepare questions about the team, product, and success measures."
            + (f"\n\nFor your current search (**{search_query}**), focus practice on the skills in each posting." if search_query else "")
        )
    if any(term in normalized for term in ("skill", "learn", "study", "roadmap")):
        if any(term in normalized for term in ("gen ai", "generative ai", "llm", "rag")) or any(
            term in search_query.lower() for term in ("gen ai", "generative ai", "llm", "rag")
        ):
            return (
                "For a GenAI/LLM role, build skills in this order:\n"
                "1. Python, APIs, Git, and basic testing.\n"
                "2. LLM APIs, structured outputs, prompt design, and evaluation.\n"
                "3. Embeddings, vector search, chunking, and RAG quality checks.\n"
                "4. Deploy a small end-to-end app and document latency, cost, and quality trade-offs.\n"
                "Use job descriptions to prioritise the exact tools employers ask for."
            )
        return (
            "Start with the skills that appear repeatedly in the roles you want. "
            "Practise each one in a small project, write down what you built and the result, "
            "then compare your project against real job descriptions."
        )
    if any(term in normalized for term in ("salary", "pay", "package", "ctc")):
        return (
            "Salary depends on location, level, company, and interview scope. Compare several "
            "recent postings for the same role and location, then check reliable salary sources. "
            "I don't have verified salary figures in the current job results, so I won't guess."
        )
    is_genai_question = any(
        term in normalized for term in ("gen ai", "genai", "generative ai", "llm", "rag")
    ) or any(
        term in search_query.lower()
        for term in ("gen ai", "genai", "generative ai", "llm", "rag")
    )
    if is_genai_question:
        years = re.search(r"\b(\d+)\s*(?:years?|yrs?)\b", normalized)
        experience = (
            f"With {years.group(1)} years of experience, " if years else "For your transition, "
        )
        answer = (
            f"{experience}your SQL background is useful for data-heavy GenAI products, "
            "evaluation datasets, and analytics. A practical transition plan:\n"
            "1. Add Python and build small API-based applications if you have not already.\n"
            "2. Learn LLM APIs, prompt design, structured outputs, and how to evaluate answers.\n"
            "3. Build a RAG project: ingest documents, create embeddings, retrieve relevant chunks, "
            "and show citations in answers.\n"
            "4. Deploy the project and document quality, latency, and cost; use it as a portfolio piece.\n"
            "Target GenAI/LLM Application Engineer or RAG Engineer roles, and check each posting's "
            "experience requirement before applying."
        )
        if "sql" in normalized:
            answer += (
                "\n\nIn interviews, connect your SQL experience to data quality, retrieval "
                "evaluation, and measuring whether generated answers are grounded in source data."
            )
        if job_list:
            answer += f"\n\nRelated openings in your current results:\n{job_list}"
        return answer
    if any(term in normalized for term in ("which job", "best job", "match", "opening", "job list")):
        if job_list:
            return f"Here are the current results to compare:\n{job_list}\n\nOpen each listing to verify its experience requirements and apply details."
        return (
            "There are no live listings loaded in this session yet. Search by role and location "
            "first; I can then help compare the returned jobs."
        )

    return (
        f"I can help with your career question. Your current search is **{search_query or 'not set'}**. "
        "I can help you plan skills, tailor a resume, prepare for interviews, or compare these roles. "
        "For more specific AI-generated answers, configure a valid Gemini API key."
    )


def _gemini_error(response: requests.Response, api_key: str) -> str:
    status = response.status_code
    detail = ""
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            detail = error["message"].strip()
    except ValueError:
        pass
    if api_key:
        detail = detail.replace(api_key, "[redacted]")

    normalized_detail = detail.lower()
    if "api key not valid" in normalized_detail or "invalid api key" in normalized_detail:
        return (
            "Gemini rejected the API key. Create a valid key in Google AI Studio and "
            "replace GEMINI_API_KEY in your local .env file."
        )
    if status in (401, 403):
        return (
            f"Gemini denied access (HTTP {status}). Check the API key and confirm the "
            "Generative Language API is enabled for its Google project."
        )
    if status == 429:
        return "Gemini quota or rate limit reached. Check the Google AI Studio project quota."
    if status == 404:
        return "The configured Gemini model is unavailable. Check model access for this API key."
    if status == 400:
        message = "Gemini rejected the request (HTTP 400). Check the API key, API access, and request."
    else:
        message = f"Gemini returned HTTP {status}."
    if detail:
        message += f" Details: {detail[:240]}"
    return message


def _gemini_answer_is_incomplete(answer: str, finish_reason: str) -> bool:
    if finish_reason == "MAX_TOKENS":
        return True
    stripped = answer.rstrip()
    if not stripped or stripped.endswith((",", ";", ":")):
        return True
    if stripped.count("(") > stripped.count(")") or stripped.count("[") > stripped.count("]"):
        return True
    return bool(
        re.search(
            r"(?:\be\.g\.|\bi\.e\.|\band|\bor|\bwith|\bsuch as|\bincluding)$",
            stripped,
            re.IGNORECASE,
        )
    )


def answer_career_question(
    question: str,
    jobs: list[dict[str, Any]],
    search_query: str,
    history: list[dict[str, str]],
    gemini_api_key: str = "",
    resume_text: str = "",
    send_resume_to_gemini: bool = False,
    location: str = "India",
) -> str:
    if _asks_for_company_names(question):
        return local_career_answer(question, jobs, search_query, location)

    if "snowflake" in question.casefold() and _asks_for_skill_development(question):
        return local_career_answer(question, jobs, search_query, location)

    if not gemini_api_key:
        return local_career_answer(question, jobs, search_query, location)

    job_context = "\n".join(
        f"- {job.get('title', 'Role')} | {job.get('company', 'Company')} | "
        f"{job.get('location', 'Location not listed')} | "
        f"{job.get('description', '')[:450]}"
        for job in jobs[:6]
    )
    system_instruction = (
        "You are Career Compass, a practical and friendly job-search career assistant. "
        "Answer the user's actual question directly, then give concise actionable guidance. "
        "Use only the provided current-job context for vacancy-specific claims; never invent "
        "openings, salaries, or company facts. Clearly say when data is unavailable. "
        "Keep answers readable with short paragraphs or bullets. Return only the finished "
        "answer; never show drafting notes, internal reasoning, or an unfinished sentence. "
        f"\nCurrent search query: {search_query or 'not set'}"
        f"\nCurrent job results:\n{job_context or 'No live job results are loaded.'}"
    )
    if resume_text and send_resume_to_gemini:
        system_instruction += (
            "\nThe user explicitly opted in to share this resume text for this answer. "
            "Use it only to answer the current question and do not repeat contact details."
            f"\nResume text:\n{resume_text[:6000]}"
        )

    contents = [
        {
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        }
        for message in history[-8:]
        if message.get("role") in ("user", "assistant") and message.get("content")
    ]
    contents.append({"role": "user", "parts": [{"text": question}]})

    try:
        models = (GEMINI_MODEL, *GEMINI_FALLBACK_MODELS)
        for index, model in enumerate(models):
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": gemini_api_key},
                    json={
                        "system_instruction": {"parts": [{"text": system_instruction}]},
                        "contents": contents,
                        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1200},
                    },
                    timeout=(8, 60),
                )
            except requests.Timeout:
                if index < len(models) - 1:
                    continue
                raise
            if not response.ok:
                error = _gemini_error(response, gemini_api_key)
                if response.status_code in (404, 503) and index < len(models) - 1:
                    continue
                raise SuggestionError(error)
            payload = response.json()
            candidate = payload["candidates"][0]
            parts = candidate["content"]["parts"]
            answer = "\n".join(
                part["text"] for part in parts if isinstance(part.get("text"), str)
            ).strip()
            if not answer:
                raise SuggestionError("Gemini returned an empty answer. Please try asking another way.")
            finish_reason = candidate.get("finishReason", "")
            if _gemini_answer_is_incomplete(answer, finish_reason):
                if index < len(models) - 1:
                    continue
                raise SuggestionError(
                    "Gemini stopped before completing its answer. Showing complete local guidance instead."
                )
            if re.search(r"\bdrafting the response\b", answer, re.IGNORECASE):
                if index < len(models) - 1:
                    continue
                raise SuggestionError(
                    "Gemini returned drafting text instead of a finished answer. "
                    "Showing complete local guidance instead."
                )
            return answer
        raise SuggestionError(
            "Gemini models are temporarily unavailable. Please try again shortly."
        )
    except requests.RequestException as exc:
        detail = "Could not reach the Gemini API."
        if isinstance(exc, requests.Timeout):
            detail = "Gemini request timed out. Check the connection or try again."
        raise SuggestionError(detail) from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SuggestionError("Gemini returned an invalid response.") from exc


def _local_suggestions(query: str, jobs: list[dict[str, Any]], resume_text: str) -> list[str]:
    titles = list(dict.fromkeys(job["title"] for job in jobs if job.get("title")))
    companies = list(dict.fromkeys(job["company"] for job in jobs if job.get("company")))
    suggestions = []
    if titles:
        suggestions.append(f"Explore related roles: {', '.join(titles[:4])}.")
    if companies:
        suggestions.append(f"Compare openings at: {', '.join(companies[:4])}.")
    if resume_text and query:
        suggestions.append(
            "Tailor your resume to the required skills in each job description before applying."
        )
    if query and not titles:
        normalized_query = query.lower()
        range_experience = re.search(
            r"\b(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)\b",
            normalized_query,
        )
        exact_experience = re.search(
            r"\b(\d+)\s*\+?\s*(?:years?|yrs?)\b",
            normalized_query,
        )
        if range_experience:
            years = f"{range_experience.group(1)}–{range_experience.group(2)} years of experience"
        elif exact_experience:
            years = f"{exact_experience.group(1)} years of experience"
        else:
            years = "your experience level"
        if any(term in normalized_query for term in ("gen ai", "genai", "generative ai", "llm", "rag")):
            suggestions.extend(
                [
                    f"With {years}, target GenAI Engineer, LLM Application Engineer, and RAG Engineer roles.",
                    "Highlight Python, LLM APIs, prompt design, RAG, embeddings/vector databases, and evaluation in your resume.",
                    "Add 1–2 project outcomes with measurable impact; confirm each vacancy's experience requirement before applying.",
                ]
            )
        elif any(term in normalized_query for term in ("machine learning", "ml engineer", "ai engineer")):
            suggestions.extend(
                [
                    f"With {years}, explore AI Engineer, Machine Learning Engineer, and Applied AI roles.",
                    "Show Python, model evaluation, deployment, and one end-to-end project with measurable results.",
                    "Check role-specific experience requirements; they vary between companies and job postings.",
                ]
            )
        else:
            suggestions.extend(
                [
                    f"Use {years} as a filter and compare the required skills across current openings.",
                    "Make your resume headline, skills, and project outcomes match the role you are targeting.",
                ]
            )
    return suggestions


def generate_suggestions(
    query: str,
    jobs: list[dict[str, Any]],
    resume_text: str = "",
    gemini_api_key: str = "",
    send_resume_to_gemini: bool = False,
) -> list[str]:
    fallback = _local_suggestions(query, jobs, resume_text)
    if not gemini_api_key:
        return fallback

    context = "\n".join(
        f"- {job.get('title', '')} at {job.get('company', '')}: "
        f"{job.get('description', '')[:500]}"
        for job in jobs[:8]
    )
    prompt = (
        "Give 3 concise, practical job-search suggestions based only on the supplied context. "
        "Do not invent vacancies, employers, or facts. Do not repeat personal contact details. "
        f"\nSearch: {query}\nJobs:\n{context or 'No job results yet.'}"
    )
    if resume_text and send_resume_to_gemini:
        prompt += f"\nResume text for skill context (private user-provided data):\n{resume_text[:6000]}"

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=(8, 25),
        )
        if not response.ok:
            raise SuggestionError(_gemini_error(response, gemini_api_key))
        payload = response.json()
        parts = payload["candidates"][0]["content"]["parts"]
        answer = "\n".join(part["text"] for part in parts if isinstance(part.get("text"), str))
        suggestions = [
            line.strip().lstrip("-•*0123456789. ")
            for line in answer.splitlines()
            if line.strip()
        ]
        return suggestions[:5] or fallback
    except requests.RequestException as exc:
        detail = "Could not reach the Gemini API."
        if isinstance(exc, requests.Timeout):
            detail = "Gemini request timed out. Check the connection or try again."
        raise SuggestionError(detail) from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SuggestionError("Gemini returned an invalid response.") from exc
