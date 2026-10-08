import unittest
from unittest.mock import Mock, patch

import requests

from job_search import (
    JobSearchError,
    search_google_jobs,
    search_google_jobs_with_fallback,
)


class GoogleJobsSearchTests(unittest.TestCase):
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
