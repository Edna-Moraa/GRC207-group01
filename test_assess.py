from datetime import date
import unittest

from assess import FAIL, INSUFFICIENT, NOT_APPLICABLE, PASS, evaluate_record

POLICY = {"maximum_review_age_days": 90, "required_review_status": "approved"}
AS_OF = date(2026, 3, 31)


class AccessReviewTests(unittest.TestCase):
    def check(self, expected, **changes):
        record = {
            "account_id": "TEST-01",
            "evidence_id": "FIXTURE-01",
            "active": True,
            "privileged": True,
            "last_review_date": "2026-03-20",
            "review_status": "approved",
        }
        record.update(changes)
        status, reason = evaluate_record(record, AS_OF, POLICY)
        self.assertEqual(status, expected)
        self.assertTrue(reason.strip())

    def test_recent_approved_review(self):
        self.check(PASS)

    def test_exactly_ninety_days(self):
        self.check(PASS, last_review_date="2025-12-31")

    def test_ninety_one_days(self):
        self.check(FAIL, last_review_date="2025-12-30")

    def test_missing_date(self):
        self.check(INSUFFICIENT, last_review_date=None)

    def test_inactive_account(self):
        self.check(NOT_APPLICABLE, active=False, last_review_date=None)

    def test_missing_scope(self):
        self.check(INSUFFICIENT, privileged=None)

    def test_future_review_date(self):
        self.check(INSUFFICIENT, last_review_date="2026-04-01")

    def test_pending_review(self):
        self.check(FAIL, review_status="pending")

    def test_invalid_date(self):
        self.check(INSUFFICIENT, last_review_date="invalid-date")    


if __name__ == "__main__":
    unittest.main()
