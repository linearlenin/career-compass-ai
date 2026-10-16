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


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) else fallback


def filter_jobs_for_location(
    location: str,
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep results in the requested city/region when the search is more specific than a country."""
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

    return [
        job
        for job in jobs
        if re.search(
            rf"\b{re.escape(target)}\b",
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
                "location": location,
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
