import unittest

from resume import match_score


class ResumeMatchTests(unittest.TestCase):
    def test_matching_terms_produce_positive_score(self):
        score = match_score(
            "Python developer with SQL and data engineering experience",
            {"title": "Python developer", "description": "Python SQL ETL"},
        )
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_empty_resume_has_zero_score(self):
        self.assertEqual(match_score("", {"title": "Python developer"}), 0)


if __name__ == "__main__":
    unittest.main()
