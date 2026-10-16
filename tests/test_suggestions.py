import unittest
from unittest.mock import Mock, patch

import requests

from suggestions import (
    GEMINI_MODEL,
    SuggestionError,
    answer_career_question,
    extract_job_search_request,
    filter_jobs_for_role,
    generate_suggestions,
    local_career_answer,
)


class SuggestionTests(unittest.TestCase):
    @patch("suggestions.requests.post")
    def test_resume_is_not_sent_to_gemini_without_opt_in(self, post):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Look at Python roles."}]}}]
        }
        post.return_value = response

        generate_suggestions(
            query="Python",
            jobs=[],
            resume_text="Private resume text",
            gemini_api_key="test-key",
        )

        body = post.call_args.kwargs["json"]
        self.assertNotIn("Private resume text", str(body))
        self.assertIn(GEMINI_MODEL, post.call_args.args[0])

    def test_without_gemini_uses_local_suggestions(self):
        suggestions = generate_suggestions(
            query="Python developer",
            jobs=[{"title": "Python Engineer", "company": "Example"}],
        )
        self.assertTrue(any("Python Engineer" in suggestion for suggestion in suggestions))

    def test_genai_guidance_works_without_live_job_results(self):
        suggestions = generate_suggestions(
            query="Gen AI Engineer 2 years",
            jobs=[],
        )
        combined = " ".join(suggestions)
        self.assertIn("2 years of experience", combined)
        self.assertIn("GenAI Engineer", combined)
        self.assertIn("RAG", combined)

    def test_experience_range_is_not_misread_as_a_single_year(self):
        suggestions = generate_suggestions(
            query="Gen AI Engineer 1-3 years",
            jobs=[],
        )
        self.assertIn("1–3 years of experience", " ".join(suggestions))

    @patch("suggestions.requests.post")
    def test_reports_invalid_gemini_key_without_leaking_key(self, post):
        api_key = "private-test-key"
        response = Mock()
        response.ok = False
        response.status_code = 400
        response.json.return_value = {
            "error": {
                "message": f"API key not valid. Received: {api_key}",
                "status": "INVALID_ARGUMENT",
            }
        }
        post.return_value = response

        with self.assertRaises(SuggestionError) as raised:
            generate_suggestions(
                query="Gen AI Engineer 2 years",
                jobs=[],
                gemini_api_key=api_key,
            )

        self.assertIn("Gemini rejected the API key", str(raised.exception))
        self.assertNotIn(api_key, str(raised.exception))

    @patch("suggestions.requests.post")
    def test_reports_gemini_quota_limit(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 429
        response.json.return_value = {
            "error": {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}
        }
        post.return_value = response

        with self.assertRaisesRegex(SuggestionError, "quota or rate limit"):
            generate_suggestions(
                query="Gen AI Engineer",
                jobs=[],
                gemini_api_key="private-test-key",
            )

    def test_chat_uses_a_specific_local_answer_without_gemini(self):
        answer = answer_career_question(
            question="What skills should I learn?",
            jobs=[],
            search_query="Gen AI Engineer 2 years",
            history=[],
        )

        self.assertIn("LLM APIs", answer)
        self.assertIn("RAG", answer)
        self.assertIn("Deploy", answer)

    @patch("suggestions.requests.post")
    def test_chat_sends_recent_conversation_and_job_context(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Prioritize the RAG role."}]}}]
        }
        post.return_value = response

        answer = answer_career_question(
            question="Which one should I choose?",
            jobs=[
                {
                    "title": "RAG Engineer",
                    "company": "Example",
                    "location": "Chennai",
                    "description": "Build retrieval systems.",
                }
            ],
            search_query="Gen AI 2 years",
            history=[
                {"role": "user", "content": "I have two years of experience."},
                {"role": "assistant", "content": "I can help compare roles."},
            ],
            gemini_api_key="test-key",
        )

        self.assertEqual(answer, "Prioritize the RAG role.")
        self.assertIn(GEMINI_MODEL, post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["timeout"], (8, 60))
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["contents"][0]["role"], "user")
        self.assertEqual(body["contents"][1]["role"], "model")
        self.assertEqual(
            body["contents"][2]["parts"][0]["text"],
            "Which one should I choose?",
        )
        self.assertIn("RAG Engineer", body["system_instruction"]["parts"][0]["text"])

    @patch("suggestions.requests.post")
    def test_chat_fails_over_when_primary_gemini_model_is_busy(self, post):
        primary = Mock()
        primary.ok = False
        primary.status_code = 503
        primary.json.return_value = {
            "error": {"message": "Model is experiencing high demand"}
        }
        fallback = Mock()
        fallback.ok = True
        fallback.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "SQL Developer roles."}]}}]
        }
        post.side_effect = [primary, fallback]

        answer = answer_career_question(
            question="I want SQL Developer roles with 3 years of experience",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="test-key",
        )

        self.assertEqual(answer, "SQL Developer roles.")
        self.assertEqual(post.call_count, 2)
        self.assertIn(GEMINI_MODEL, post.call_args_list[0].args[0])
        self.assertIn("gemini-3.5-flash", post.call_args_list[1].args[0])

    @patch("suggestions.requests.post")
    def test_chat_fails_over_when_primary_gemini_model_times_out(self, post):
        fallback = Mock()
        fallback.ok = True
        fallback.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Python Developer roles."}]}}]
        }
        post.side_effect = [requests.Timeout(), fallback]

        answer = answer_career_question(
            question="Find current Python Developer roles",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="test-key",
        )

        self.assertEqual(answer, "Python Developer roles.")
        self.assertEqual(post.call_count, 2)

    def test_local_chat_answers_questions_about_current_job_results(self):
        answer = local_career_answer(
            question="Which job openings should I compare?",
            jobs=[
                {
                    "title": "SQL Developer",
                    "company": "Example Bank",
                    "location": "Chennai",
                }
            ],
            search_query="SQL developer",
        )

        self.assertIn("SQL Developer", answer)
        self.assertIn("Example Bank", answer)

    def test_local_chat_answers_sql_to_genai_transition_question(self):
        answer = answer_career_question(
            question="I have 2 years experience in SQL. How can I move to a GenAI role?",
            jobs=[],
            search_query="",
            history=[],
        )

        self.assertIn("2 years of experience", answer)
        self.assertIn("SQL background", answer)
        self.assertIn("RAG project", answer)
        self.assertIn("GenAI/LLM Application Engineer", answer)

    def test_local_chat_understands_oracle_developer_request_with_two_years(self):
        answer = answer_career_question(
            question="i want oracle dev with 2yrs exp",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("2 years of experience", answer)
        self.assertIn("Oracle Developer", answer)
        self.assertIn("PL/SQL Developer", answer)
        self.assertIn("stored procedures", answer)
        self.assertIn("Search Oracle Developer jobs", answer)
        self.assertIn("India", answer)

    def test_oracle_chat_lists_matching_live_roles_when_available(self):
        answer = local_career_answer(
            question="I want an Oracle Developer job with 2 years experience",
            jobs=[
                {
                    "title": "PL/SQL Developer",
                    "company": "Example Bank",
                    "location": "Chennai",
                    "description": "Develop Oracle stored procedures.",
                },
                {
                    "title": "Python Engineer",
                    "company": "Another Company",
                    "location": "Pune",
                    "description": "Build Python APIs.",
                },
            ],
            location="India",
        )

        self.assertIn("PL/SQL Developer", answer)
        self.assertIn("Example Bank", answer)
        self.assertNotIn("Another Company", answer)

    def test_local_chat_understands_snowflake_developer_request_with_three_years(self):
        answer = answer_career_question(
            question="i want snowflake dev with 3 yrs exp",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("3 years of experience", answer)
        self.assertIn("Snowflake Developer", answer)
        self.assertIn("Snowflake Data Engineer", answer)
        self.assertIn("Snowflake SQL", answer)
        self.assertIn("Search Snowflake Developer jobs", answer)
        self.assertIn("India", answer)

    def test_snowflake_chat_lists_matching_live_roles_when_available(self):
        answer = local_career_answer(
            question="I want a Snowflake developer role with 3 years experience",
            jobs=[
                {
                    "title": "Snowflake Data Engineer",
                    "company": "Example Data Co",
                    "location": "Bengaluru",
                    "description": "Build Snowflake ELT pipelines.",
                },
                {
                    "title": "Oracle Developer",
                    "company": "Other Company",
                    "location": "Pune",
                    "description": "Develop Oracle stored procedures.",
                },
            ],
            location="India",
        )

        self.assertIn("Snowflake Data Engineer", answer)
        self.assertIn("Example Data Co", answer)
        self.assertNotIn("Other Company", answer)

    def test_chat_handles_an_arbitrary_role_with_experience_not_a_known_vendor(self):
        answer = answer_career_question(
            question="I want a backend developer with 4 yrs exp",
            jobs=[],
            search_query="",
            history=[],
            location="Bengaluru",
        )

        self.assertIn("4 years of experience", answer)
        self.assertIn("Backend Developer", answer)
        self.assertIn("Bengaluru", answer)
        self.assertIn("Search Backend Developer jobs", answer)

    def test_chat_handles_sql_developer_abbreviation_with_three_years(self):
        answer = answer_career_question(
            question="i want sql dev with 3 yr exp",
            jobs=[],
            search_query="",
            history=[],
        )

        self.assertIn("3 years of experience", answer)
        self.assertIn("SQL Developer", answer)
        self.assertIn("Search SQL Developer jobs", answer)

    def test_chat_handles_sql_developer_request_with_experience_before_role_and_typo(self):
        answer = answer_career_question(
            question="i want 3 yrs exp sql devloper role",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("3 years of experience", answer)
        self.assertIn("SQL Developer", answer)
        self.assertIn("SQL query writing and optimisation", answer)
        self.assertIn("Search SQL Developer jobs", answer)

    def test_current_python_job_request_extracts_role_and_city(self):
        self.assertEqual(
            extract_job_search_request("i want current python dev role in chennai"),
            ("Python Developer", "Python Developer jobs", "Chennai"),
        )

    def test_role_only_chat_request_without_experience_triggers_live_search(self):
        self.assertEqual(
            extract_job_search_request("I want full stack developer role"),
            (
                "Full-Stack Developer",
                "Full-Stack Developer jobs",
                "India",
            ),
        )
        self.assertEqual(
            extract_job_search_request("I want frontend roles in Chennai"),
            ("Frontend Developer", "Frontend Developer jobs", "Chennai"),
        )

    def test_genai_fresher_request_extracts_entry_level_job_search(self):
        self.assertEqual(
            extract_job_search_request("i wan gen ai dev for fresher"),
            ("GenAI Developer", "GenAI Developer fresher jobs", "India"),
        )
        self.assertEqual(
            extract_job_search_request("i want gen ai role for fresher"),
            ("GenAI Developer", "GenAI Developer fresher jobs", "India"),
        )

    def test_fresher_preparation_question_is_not_misrouted_to_job_search(self):
        question = "I want prepare for fresher java developer role"

        self.assertIsNone(extract_job_search_request(question))

        answer = local_career_answer(question, [], location="India")
        self.assertIn("fresher **Java Developer** role", answer)
        self.assertIn("object-oriented programming", answer)
        self.assertNotIn("Prepare jobs", answer)

    def test_genai_fresher_request_gives_portfolio_guidance_and_live_search(self):
        answer = answer_career_question(
            question="i wan gen ai dev for fresher",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("As a fresher", answer)
        self.assertIn("GenAI Developer", answer)
        self.assertIn("LLM Application Developer", answer)
        self.assertIn("Python, LLM APIs, prompt design, embeddings, and RAG", answer)
        self.assertIn("Search GenAI Developer jobs", answer)
        self.assertIn("fresher", answer)

    def test_genai_fresher_matches_genai_jobs_not_generic_ai_mentions(self):
        answer = local_career_answer(
            question="i wan gen ai dev for fresher",
            jobs=[
                {
                    "title": "Generative AI Intern",
                    "company": "Example AI",
                    "location": "Chennai",
                    "description": "Build RAG prototypes.",
                },
                {
                    "title": "AI Support Analyst",
                    "company": "Generic Systems",
                    "location": "Pune",
                    "description": "Provide support for AI-powered workflows.",
                },
            ],
        )

        self.assertIn("Example AI", answer)
        self.assertNotIn("Generic Systems", answer)

    def test_current_python_job_request_returns_matching_live_results(self):
        answer = local_career_answer(
            question="i want current python dev role in chennai",
            jobs=[
                {
                    "title": "Python Developer",
                    "company": "Example Systems",
                    "location": "Chennai",
                },
                {
                    "title": "Java Developer",
                    "company": "Other Systems",
                    "location": "Chennai",
                },
            ],
        )

        self.assertIn("Example Systems", answer)
        self.assertIn("Chennai", answer)
        self.assertNotIn("Other Systems", answer)

    def test_current_python_job_request_has_specific_fallback_without_live_results(self):
        answer = answer_career_question(
            question="i want current python dev role in chennai",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("Python Developer", answer)
        self.assertIn("Chennai", answer)
        self.assertIn("Search Python Developer jobs in Chennai", answer)

    def test_chat_uses_available_gemini_model(self):
        self.assertEqual(GEMINI_MODEL, "gemini-3.6-flash")

    def test_chat_handles_python_developer_with_five_years(self):
        answer = answer_career_question(
            question="i want python dev with 5 yr exp",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("5 years of experience", answer)
        self.assertIn("Python Developer", answer)
        self.assertIn("Search Python Developer jobs", answer)

    def test_chat_handles_java_role_with_five_plus_years_and_searches_live_jobs(self):
        self.assertEqual(
            extract_job_search_request("i want 5+ yrs java role"),
            ("Java Developer", "Java Developer 5+ years experience jobs", "India"),
        )

        answer = answer_career_question(
            question="i want 5+ yrs java role",
            jobs=[],
            search_query="",
            history=[],
            gemini_api_key="",
        )

        self.assertIn("5+ years of experience", answer)
        self.assertIn("Java Developer", answer)
        self.assertIn("Search Java Developer jobs", answer)

    def test_role_search_supports_it_roles_and_one_through_ten_years(self):
        role_examples = {
            "AI Engineer": "AI Engineer",
            "Application Developer": "Application Developer",
            "Backend Developer": "Backend Developer",
            "Blockchain Developer": "Blockchain Developer",
            "Business Analyst (IT)": "Business Analyst (IT)",
            "Cloud Engineer": "Cloud Engineer",
            "Cybersecurity Engineer": "Cybersecurity Engineer",
            "Data Analyst": "Data Analyst",
            "Data Engineer": "Data Engineer",
            "Data Scientist": "Data Scientist",
            "Database Administrator": "Database Administrator",
            "DevOps Engineer": "DevOps Engineer",
            "Embedded Systems Engineer": "Embedded Systems Engineer",
            "Frontend Developer": "Frontend Developer",
            "Full‑Stack Developer": "Full-Stack Developer",
            "Game Developer": "Game Developer",
            "IT Support Specialist": "IT Support Specialist",
            "Machine Learning Engineer": "Machine Learning Engineer",
            "Mobile App Developer (Android/iOS)": "Mobile App Developer (Android/iOS)",
            "Network Engineer": "Network Engineer",
            "Product Manager (Tech)": "Product Manager (Tech)",
            "QA Engineer": "QA Engineer",
            "QA Engineer / Test Automation Engineer": "QA Engineer / Test Automation Engineer",
            "Robotics Engineer": "Robotics Engineer",
            "Site Reliability Engineer (SRE)": "Site Reliability Engineer (SRE)",
            "Software Engineer": "Software Engineer",
            "Solutions Architect": "Solutions Architect",
            "System Administrator": "System Administrator",
            "UI/UX Designer": "UI/UX Designer",
            "Web Developer": "Web Developer",
        }
        for requested_role, expected_role in role_examples.items():
            with self.subTest(role=requested_role):
                role, query, location = extract_job_search_request(
                    f"I want {requested_role} role with 3 yrs exp"
                )
                self.assertEqual(role, expected_role)
                self.assertIn(expected_role, query)
                self.assertEqual(location, "India")

        for years in range(1, 11):
            with self.subTest(years=years):
                role, query, _ = extract_job_search_request(
                    f"I want Cloud Engineer with {years} years experience"
                )
                self.assertEqual(role, "Cloud Engineer")
                unit = "year" if years == 1 else "years"
                self.assertIn(f"{years} {unit} experience", query)

    def test_role_search_supports_experience_ranges_and_ellipsis(self):
        for phrase, expected_query in (
            ("I want Data Engineer with 1-10 years experience", "1-10 years experience"),
            ("I want Data Engineer with 1 to 10 years experience", "1-10 years experience"),
            ("I want Data Engineer with 1...10 years experience", "1-10 years experience"),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    extract_job_search_request(phrase),
                    ("Data Engineer", f"Data Engineer {expected_query} jobs", "India"),
                )

    def test_frontend_role_after_experience_is_parsed_as_frontend_developer(self):
        self.assertEqual(
            extract_job_search_request("i want 2 yrs exp role in front end role"),
            (
                "Frontend Developer",
                "Frontend Developer 2 years experience jobs",
                "India",
            ),
        )

    def test_internship_role_and_location_are_parsed_for_live_search(self):
        self.assertEqual(
            extract_job_search_request("I want internship role in Bangalore"),
            ("Internship", "Internship jobs", "Bangalore"),
        )

    def test_internship_request_with_common_typo_is_parsed_for_live_search(self):
        self.assertEqual(
            extract_job_search_request(
                "i want python developer intership role in chennai"
            ),
            (
                "Python Developer",
                "Python Developer internship jobs",
                "Chennai",
            ),
        )

    def test_abbreviated_developer_internship_roles_are_normalized(self):
        role_cases = (
            ("python dev", "Python Developer"),
            ("java dev", "Java Developer"),
            ("sql dev", "SQL Developer"),
        )
        for requested_role, expected_role in role_cases:
            with self.subTest(role=requested_role):
                self.assertEqual(
                    extract_job_search_request(
                        f"I want {requested_role} internship in Bangalore"
                    ),
                    (
                        expected_role,
                        f"{expected_role} internship jobs",
                        "Bangalore",
                    ),
                )

    def test_experience_ranges_and_ten_plus_are_parsed_for_search(self):
        cases = (
            (
                "I want Java Developer with 6-7 years experience in Delhi",
                "Java Developer",
                "Java Developer 6-7 years experience jobs",
                "Delhi",
            ),
            (
                "I want 7-10 yrs exp Python Developer in Noida",
                "Python Developer",
                "Python Developer 7-10 years experience jobs",
                "Noida",
            ),
            (
                "I want 10+ years SQL Developer in Hyderabad",
                "SQL Developer",
                "SQL Developer 10+ years experience jobs",
                "Hyderabad",
            ),
        )
        for question, expected_role, expected_query, expected_location in cases:
            with self.subTest(question=question):
                self.assertEqual(
                    extract_job_search_request(question),
                    (expected_role, expected_query, expected_location),
                )

    def test_salary_requirement_is_preserved_in_provider_search(self):
        self.assertEqual(
            extract_job_search_request(
                "I want 15 yrs exp Java role above 20 LPA in Hyderabad"
            ),
            (
                "Java Developer",
                "Java Developer 15 years experience above 20 LPA jobs",
                "Hyderabad",
            ),
        )
        self.assertEqual(
            extract_job_search_request("I want Dev role above 7 LPA in Chennai"),
            ("Developer", "Developer jobs above 7 LPA", "Chennai"),
        )

    def test_frontend_filter_accepts_front_end_titles_and_rejects_backend(self):
        matches = filter_jobs_for_role(
            "Frontend Developer",
            [
                {"title": "Front-End Developer"},
                {"title": "Frontend Engineer"},
                {"title": "Backend Developer"},
            ],
        )

        self.assertEqual(
            [job["title"] for job in matches],
            ["Front-End Developer", "Frontend Engineer"],
        )

    def test_internship_filter_keeps_intern_titles(self):
        matches = filter_jobs_for_role(
            "Internship",
            [
                {"title": "Software Engineering Intern"},
                {"title": "Frontend Developer"},
            ],
        )

        self.assertEqual([job["title"] for job in matches], ["Software Engineering Intern"])

    def test_role_internship_filter_accepts_related_intern_titles(self):
        matches = filter_jobs_for_role(
            "Python Developer Internship",
            [
                {"title": "Python Developer Intern"},
                {"title": "Python Development Internship"},
                {"title": "Software Engineering Intern"},
                {"title": "Python Developer"},
            ],
        )

        self.assertEqual(
            [job["title"] for job in matches],
            ["Python Developer Intern", "Python Development Internship"],
        )

    def test_live_python_internship_listings_are_returned_by_career_assistant(self):
        answer = local_career_answer(
            question="i want python developer intership role in chennai",
            jobs=[
                {
                    "title": "Python Development Internship",
                    "company": "Chennai Python Co",
                    "location": "Chennai, Tamil Nadu",
                },
                {
                    "title": "Python Developer",
                    "company": "Full-Time Python Co",
                    "location": "Chennai, Tamil Nadu",
                },
            ],
            search_query="Python Developer internship jobs",
            location="Chennai",
        )

        self.assertIn("Chennai Python Co", answer)
        self.assertNotIn("Full-Time Python Co", answer)

    def test_production_support_search_uses_it_specific_provider_query(self):
        self.assertEqual(
            extract_job_search_request("i want 5 yrs production support role"),
            (
                "Production Support",
                "Application Production Support Engineer 5 years experience jobs",
                "India",
            ),
        )

    def test_production_support_search_recognizes_plus_exp_shorthand(self):
        self.assertEqual(
            extract_job_search_request("i want 4+ exp production support role"),
            (
                "Production Support",
                "Application Production Support Engineer 4+ years experience jobs",
                "India",
            ),
        )

    def test_company_follow_up_lists_companies_from_current_results(self):
        answer = local_career_answer(
            question="may i know the company",
            jobs=[
                {
                    "title": "Production Support Engineer",
                    "company": "Example Bank",
                    "location": "Chennai",
                },
                {
                    "title": "Application Support Analyst",
                    "company": "Example Systems",
                    "location": "Bengaluru",
                },
                {
                    "title": "Product Support Engineer",
                    "company": "Unrelated Product Co",
                    "location": "Bengaluru",
                },
            ],
            search_query="Application Production Support Engineer 4 years experience jobs",
        )

        self.assertIn("Example Bank", answer)
        self.assertNotIn("Example Systems", answer)
        self.assertNotIn("Unrelated Product Co", answer)
        self.assertIn("Production Support Engineer", answer)
        self.assertNotIn("no live job listings", answer.lower())

    @patch("suggestions.requests.post")
    def test_company_follow_up_uses_loaded_results_without_calling_gemini(self, post):
        answer = answer_career_question(
            question="may i know the company",
            jobs=[
                {
                    "title": "Production Support Engineer",
                    "company": "Example Bank",
                    "location": "Chennai",
                }
            ],
            search_query="Application Production Support Engineer 4+ years experience jobs",
            history=[],
            gemini_api_key="test-key",
        )

        self.assertIn("Example Bank", answer)
        post.assert_not_called()

    def test_production_support_matches_exclude_manufacturing_production_jobs(self):
        answer = local_career_answer(
            question="i want 5 yrs production support role",
            jobs=[
                {
                    "title": "Production Support Engineer",
                    "company": "Application Services Co",
                    "location": "Chennai",
                },
                {
                    "title": "Production Supervisor",
                    "company": "Factory Co",
                    "location": "Pune",
                },
                {
                    "title": "Production Operator",
                    "company": "Manufacturing Co",
                    "location": "Mumbai",
                },
            ],
        )

        self.assertIn("Application Services Co", answer)
        self.assertNotIn("Factory Co", answer)
        self.assertNotIn("Manufacturing Co", answer)

    def test_sql_role_matching_does_not_use_unrelated_job_description_keywords(self):
        answer = local_career_answer(
            question="I want SQL Developer with 3 years experience",
            jobs=[
                {
                    "title": "Python Developer",
                    "company": "Python Co",
                    "location": "Chennai",
                    "description": "Occasional SQL query maintenance.",
                },
                {
                    "title": "SQL Developer",
                    "company": "Database Co",
                    "location": "Chennai",
                    "description": "Build SQL applications.",
                },
            ],
        )

        self.assertIn("Database Co", answer)
        self.assertNotIn("Python Co", answer)

    def test_ai_engineer_matching_excludes_ai_support_titles(self):
        answer = local_career_answer(
            question="I want AI Engineer with 2 years experience",
            jobs=[
                {
                    "title": "AI Support Analyst",
                    "company": "Support Co",
                    "location": "Chennai",
                    "description": "Support AI engineering teams.",
                },
                {
                    "title": "AI Engineer",
                    "company": "Engineering Co",
                    "location": "Bengaluru",
                },
            ],
        )

        self.assertIn("Engineering Co", answer)
        self.assertNotIn("Support Co", answer)

    def test_chat_handles_role_written_before_experience_without_a_request_phrase(self):
        answer = local_career_answer(
            question="Data Analyst with 3 years experience",
            jobs=[],
            location="Chennai",
        )

        self.assertIn("3 years of experience", answer)
        self.assertIn("Data Analyst", answer)
        self.assertIn("Chennai", answer)

    def test_experience_statement_without_a_requested_role_is_not_misread(self):
        answer = local_career_answer(
            question="I have 2 years experience in SQL. How can I move to a GenAI role?",
            jobs=[],
        )

        self.assertIn("GenAI", answer)
        self.assertIn("RAG project", answer)
        self.assertNotIn("I Have roles", answer)


if __name__ == "__main__":
    unittest.main()
