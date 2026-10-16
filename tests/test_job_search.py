import unittest
from unittest.mock import Mock, patch

import requests

from job_search import (
    JobSearchError,
    alternate_location_names,
    filter_jobs_for_location,
    search_google_jobs,
    search_google_jobs_with_fallback,
)


class GoogleJobsSearchTests(unittest.TestCase):
    def test_specific_location_keeps_only_matching_city_results(self):
        jobs = [
            {"title": "Developer", "location": "Chennai, Tamil Nadu"},
            {"title": "Developer", "location": "Bengaluru, Karnataka"},
            {"title": "Developer", "location": "New Delhi"},
        ]

        matches = filter_jobs_for_location("Chennai", jobs)

        self.assertEqual([job["location"] for job in matches], ["Chennai, Tamil Nadu"])

    def test_hierarchical_location_uses_the_most_specific_part(self):
        jobs = [
            {"location": "Chennai, Tamil Nadu, India"},
            {"location": "Coimbatore, Tamil Nadu, India"},
            {"location": "Bengaluru, Karnataka, India"},
        ]

        matches = filter_jobs_for_location("Chennai, Tamil Nadu, India", jobs)

        self.assertEqual([job["location"] for job in matches], ["Chennai, Tamil Nadu, India"])

    def test_bangalore_search_keeps_bengaluru_provider_results(self):
        jobs = [
            {"title": "SQL Developer Intern", "location": "Bengaluru, Karnataka, India"},
            {"title": "SQL Developer Intern", "location": "Hyderabad, Telangana, India"},
        ]

        matches = filter_jobs_for_location("Bangalore", jobs)

        self.assertEqual(
            [job["location"] for job in matches],
            ["Bengaluru, Karnataka, India"],
        )

    def test_bengaluru_search_keeps_bangalore_provider_results(self):
        jobs = [
            {"location": "Bangalore, Karnataka"},
            {"location": "Hyderabad, Telangana"},
        ]

        matches = filter_jobs_for_location("Bengaluru", jobs)

        self.assertEqual([job["location"] for job in matches], ["Bangalore, Karnataka"])

    def test_bangalore_search_has_bengaluru_provider_fallback(self):
        self.assertEqual(alternate_location_names("Bangalore"), ["Bengaluru"])
        self.assertEqual(
            alternate_location_names("Bangalore, Karnataka, India"),
            ["Bengaluru"],
        )

    def test_bengaluru_search_has_bangalore_provider_fallback(self):
        self.assertEqual(alternate_location_names("Bengaluru"), ["Bangalore"])

    def test_locations_without_known_aliases_have_no_fallback(self):
        self.assertEqual(alternate_location_names("Hyderabad"), [])

    def test_common_indian_city_aliases_match_and_retry(self):
        city_aliases = (
            ("Delhi", "New Delhi"),
            ("Kochi", "Cochin"),
            ("Mangaluru", "Mangalore"),
            ("Mysuru", "Mysore"),
            ("Puducherry", "Pondicherry"),
            ("Thiruvananthapuram", "Trivandrum"),
            ("Visakhapatnam", "Vizag"),
        )
        for requested, provider_location in city_aliases:
            with self.subTest(city=requested):
                self.assertIn(provider_location, alternate_location_names(requested))
                matches = filter_jobs_for_location(
                    requested,
                    [{"location": f"{provider_location}, India"}],
                )
                self.assertEqual(len(matches), 1)

    def test_country_search_preserves_provider_city_results(self):
        jobs = [
            {"location": "Chennai, Tamil Nadu"},
            {"location": "Bengaluru, Karnataka"},
        ]

        self.assertEqual(filter_jobs_for_location("India", jobs), jobs)

    def test_remote_search_only_keeps_remote_listings(self):
        jobs = [
            {"location": "Remote"},
            {"location": "Anywhere"},
            {"location": "Chennai, Tamil Nadu"},
        ]

        matches = filter_jobs_for_location("Remote", jobs)

        self.assertEqual([job["location"] for job in matches], ["Remote", "Anywhere"])

    @patch("job_search.requests.get")
    def test_normalizes_job_results_and_apply_links(self, get):
        response = Mock()
        response.json.return_value = {
            "jobs_results": [
                {
                    "title": "Python Developer",
                    "company_name": "Example Ltd",
                    "location": "Chennai",
                    "via": "Example Careers",
                    "description": "Build Python services",
                    "apply_options": [
                        {"title": "Company site", "link": "https://example.com/jobs/1"}
                    ],
                    "detected_extensions": {"posted_at": "2 days ago"},
                }
            ]
        }
        get.return_value = response

        jobs = search_google_jobs("Python developer", "Chennai", "test-key")

        self.assertEqual(jobs[0]["title"], "Python Developer")
        self.assertEqual(jobs[0]["apply_links"][0]["link"], "https://example.com/jobs/1")
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"]["engine"], "google_jobs")

    @patch("job_search.requests.get")
    def test_reports_invalid_api_key_as_provider_error(self, get):
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"error": "Invalid API key"}
        get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)

        with self.assertRaisesRegex(JobSearchError, "rejected the API key"):
            search_google_jobs("Python developer", "Chennai", "secret-key")

    @patch("job_search.requests.get")
    def test_reports_quota_limit_as_provider_error(self, get):
        response = Mock()
        response.status_code = 429
        response.json.return_value = {"error": "Monthly search limit reached"}
        get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)

        with self.assertRaisesRegex(JobSearchError, "quota or rate limit"):
            search_google_jobs("Python developer", "Chennai", "secret-key")

    @patch("job_search.requests.get")
    def test_reports_network_timeout_without_calling_it_an_api_key_error(self, get):
        get.side_effect = requests.Timeout()

        with self.assertRaisesRegex(JobSearchError, "timed out"):
            search_google_jobs("Python developer", "Chennai", "secret-key")

    @patch("job_search.requests.get")
    def test_role_search_retries_with_broader_query_after_timeout(self, get):
        response = Mock()
        response.json.return_value = {
            "jobs_results": [
                {
                    "title": "Production Support Engineer",
                    "company_name": "Example Systems",
                    "location": "India",
                }
            ]
        }
        get.side_effect = [requests.Timeout(), response]

        jobs, notice = search_google_jobs_with_fallback(
            query="Production Support 5 years experience jobs",
            fallback_query="Production Support jobs",
            location="India",
            api_key="test-key",
        )

        self.assertEqual(jobs[0]["title"], "Production Support Engineer")
        self.assertIn("experience-specific search was unavailable", notice)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[1].kwargs["params"]["q"],
            "Production Support jobs",
        )

    @patch("job_search.requests.get")
    def test_role_search_retries_broader_query_when_exact_search_has_no_results(self, get):
        exact_response = Mock()
        exact_response.json.return_value = {"jobs_results": []}
        broad_response = Mock()
        broad_response.json.return_value = {
            "jobs_results": [
                {
                    "title": "Production Support Specialist",
                    "company_name": "Example Systems",
                    "location": "India",
                }
            ]
        }
        get.side_effect = [exact_response, broad_response]

        jobs, notice = search_google_jobs_with_fallback(
            query="Production Support 5 years experience jobs",
            fallback_query="Production Support jobs",
            location="India",
            api_key="test-key",
        )

        self.assertEqual(jobs[0]["title"], "Production Support Specialist")
        self.assertIn("No listings matched the exact experience search", notice)
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
