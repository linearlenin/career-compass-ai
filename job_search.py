import re
from typing import Any

import requests


class JobSearchError(Exception):
    """Raised when the configured job search provider cannot return results."""


_COUNTRY_LOCATIONS = {
    "australia",
    "canada",
    "france",
    "germany",
    "india",
    "ireland",
    "japan",
    "netherlands",
    "new zealand",
    "singapore",
    "united arab emirates",
    "united kingdom",
    "united states",
    "uae",
    "uk",
    "usa",
    "us",
}

_LOCATION_ALIASES = (
    {"bangalore", "bengaluru"},
    {"bombay", "mumbai"},
    {"calcutta", "kolkata"},
    {"cochin", "kochi"},
    {"delhi", "new delhi"},
    {"madras", "chennai"},
    {"mangalore", "mangaluru"},
    {"mysore", "mysuru"},
    {"pondicherry", "puducherry"},
    {"simla", "shimla"},
    {"trivandrum", "thiruvananthapuram"},
    {"vizag", "visakhapatnam"},
    {"gurgaon", "gurugram"},
)

_INDIAN_REGION_NAMES = {
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andaman nicobar islands": "Andaman and Nicobar Islands",
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chandigarh": "Chandigarh",
    "chhattisgarh": "Chhattisgarh",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "delhi": "Delhi",
    "nct of delhi": "Delhi",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jammu and kashmir": "Jammu and Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "tn": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "uttaranchal": "Uttarakhand",
    "west bengal": "West Bengal",
}


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) else fallback


def normalize_search_location(location: str) -> str:
    """Canonicalize Indian state names before sending location to SerpAPI."""
    parts = [
        re.sub(r"\s+district$", "", part.strip(), flags=re.IGNORECASE)
        for part in location.split(",")
        if part.strip()
    ]
    canonical_parts = []
    has_indian_region = False
    has_india = False
    for part in parts:
        key = re.sub(r"[^a-z0-9]+", " ", part.casefold()).strip()
        if key in {"india", "bharat"}:
            canonical_parts.append("India")
            has_india = True
        elif key in _INDIAN_REGION_NAMES:
            canonical_parts.append(_INDIAN_REGION_NAMES[key])
            has_indian_region = True
        else:
            canonical_parts.append(part)
    if has_indian_region and not has_india:
        canonical_parts.append("India")
    return ", ".join(canonical_parts) or "India"


def build_job_search_queries(
    search_terms: list[str],
    experience: str,
) -> tuple[str, str]:
    """Build an experience-focused query and a broader role query for provider retry."""
    primary_terms = [*search_terms]
    fallback_terms = [*search_terms]

    if experience == "Internship":
        primary_terms.append(experience.lower())
        fallback_terms.append(experience.lower())
    elif experience.casefold() in ("fresher", "fresher (0 years)", "0 years"):
        primary_terms.append("fresher")
        fallback_terms.append("fresher")
    elif experience != "Any":
        experience_match = re.fullmatch(
            r"\s*(\d+)\s*(\+)?\s*(?:[-–]\s*(\d+)\s*)?years?\s*",
            experience,
            re.IGNORECASE,
        )
        if experience_match:
            start, plus, end = experience_match.groups()
            range_text = f"{start}-{end}" if end else f"{start}{plus or ''}"
            year_label = "year" if not end and int(start) == 1 and not plus else "years"
            primary_terms.append(f"{range_text} {year_label} experience")
        else:
            primary_terms.append(experience)

    return " ".join(primary_terms), " ".join(fallback_terms)


def alternate_location_names(location: str) -> list[str]:
    """Return known alternate spellings for a specific searched city."""
    location_parts = [
        re.sub(r"[^a-z0-9]+", " ", part.casefold()).strip()
        for part in location.split(",")
    ]
    location_parts = [
        part for part in location_parts if part and part not in _COUNTRY_LOCATIONS
    ]
    target = location_parts[0] if location_parts else ""
    aliases = next(
        (group for group in _LOCATION_ALIASES if target in group),
        set(),
    )
    return sorted(alias.title() for alias in aliases if alias != target)


def filter_jobs_for_location(
    location: str,
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep results in the requested city/region when the search is more specific than a country."""
    location = normalize_search_location(location)
    requested = re.sub(r"[^a-z0-9]+", " ", location.casefold()).strip()
    if not requested or requested in _COUNTRY_LOCATIONS:
        return jobs

    # For hierarchical inputs such as "Chennai, Tamil Nadu, India", use the
    # most specific part while allowing provider location labels to vary.
    location_parts = [
        re.sub(r"[^a-z0-9]+", " ", part.casefold()).strip()
        for part in location.split(",")
    ]
    location_parts = [part for part in location_parts if part and part not in _COUNTRY_LOCATIONS]
    target = location_parts[0] if location_parts else requested

    if target == "remote":
        return [
            job
            for job in jobs
            if re.search(r"\b(?:remote|anywhere)\b", str(job.get("location", "")), re.IGNORECASE)
        ]

    aliases = next(
        (group for group in _LOCATION_ALIASES if target in group),
        {target},
    )
    location_pattern = r"\b(?:" + "|".join(re.escape(alias) for alias in aliases) + r")\b"
    return [
        job
        for job in jobs
        if re.search(
            location_pattern,
            re.sub(r"[^a-z0-9]+", " ", str(job.get("location", "")).casefold()),
        )
    ]


def search_google_jobs(query: str, location: str, api_key: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_jobs",
                "q": query,
                "location": normalize_search_location(location),
                "api_key": api_key,
            },
            timeout=(8, 25),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else None
        provider_message = ""
        if response is not None:
            try:
                body = response.json()
                if isinstance(body, dict) and isinstance(body.get("error"), str):
                    provider_message = body["error"].strip()
            except ValueError:
                pass
        if status in (401, 403):
            message = "SerpAPI rejected the API key. Check SERPAPI_API_KEY in your .env or Streamlit Secrets."
        elif status == 429:
            message = "SerpAPI quota or rate limit reached. Check your SerpAPI dashboard and plan."
        elif status is not None and status >= 500:
            message = f"SerpAPI is temporarily unavailable (HTTP {status}). Try again shortly."
        else:
            message = f"SerpAPI returned HTTP {status or 'error'}."
        if provider_message:
            message = f"{message} Details: {provider_message[:240]}"
        raise JobSearchError(message) from exc
    except requests.exceptions.SSLError as exc:
        raise JobSearchError(
            "Secure connection to SerpAPI failed. Check your antivirus/proxy HTTPS inspection, "
            "system date, or certificate configuration."
        ) from exc
    except requests.exceptions.ProxyError as exc:
        raise JobSearchError(
            "Connection through your configured proxy failed. Check HTTPS_PROXY/HTTP_PROXY settings."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise JobSearchError(
            "SerpAPI connection timed out. The service or network may be slow; try again."
        ) from exc
    except requests.RequestException as exc:
        raise JobSearchError(
            f"Could not connect to SerpAPI ({type(exc).__name__}). "
            "Check your network, DNS, firewall, and proxy settings."
        ) from exc
    except ValueError as exc:
        raise JobSearchError("The job search provider returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise JobSearchError("SerpAPI returned an unexpected response format.")
    if payload.get("error"):
        provider_message = payload["error"]
        if not isinstance(provider_message, str):
            provider_message = "Unknown provider error"
        raise JobSearchError(f"SerpAPI error: {provider_message[:300]}")

    normalized = []
    results = payload.get("jobs_results", [])
    if not isinstance(results, list):
        raise JobSearchError("SerpAPI returned an unexpected jobs-results format.")
    for item in results:
        if not isinstance(item, dict):
            continue
        apply_options = item.get("apply_options") or []
        links = [
            {"title": _text(option.get("title"), "Apply"), "link": option["link"]}
            for option in apply_options
            if isinstance(option, dict) and isinstance(option.get("link"), str)
        ]
        detected = item.get("detected_extensions") or {}
        extensions = item.get("extensions") or []
        normalized.append(
            {
                "title": _text(item.get("title"), "Untitled role"),
                "company": _text(item.get("company_name"), "Company not listed"),
                "location": _text(item.get("location"), "Location not listed"),
                "via": _text(item.get("via")),
                "description": _text(item.get("description")),
                "apply_links": links,
                "posted_at": _text(detected.get("posted_at")),
                "salary": _text(detected.get("salary")),
                "extensions": extensions if isinstance(extensions, list) else [],
            }
        )
    return normalized


def search_google_jobs_with_fallback(
    query: str,
    fallback_query: str,
    location: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str]:
    try:
        jobs = search_google_jobs(query, location, api_key)
    except JobSearchError as primary_error:
        try:
            jobs = search_google_jobs(fallback_query, location, api_key)
        except JobSearchError as fallback_error:
            raise JobSearchError(
                f"Detailed search failed: {primary_error} "
                f"Broader role search failed: {fallback_error}"
            ) from fallback_error
        if not jobs:
            raise primary_error
        return (
            jobs,
            "The experience-specific search was unavailable; showing broader role results. "
            "Check each listing for its experience requirements.",
        )

    if jobs or query == fallback_query:
        return jobs, ""

    jobs = search_google_jobs(fallback_query, location, api_key)
    if jobs:
        return (
            jobs,
            "No listings matched the exact experience search; showing broader role results. "
            "Check each listing for its experience requirements.",
        )
    return jobs, ""
