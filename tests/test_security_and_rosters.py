import csv
import io
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException, Request
from server.controllers import auth as auth_controller
from server.models import User, UserRole
from server.services.login_rate_limit import LoginRateLimiter
from server.services.permissions import Permission, allowed
from server.services.security import hash_password
from server.schemas import LoginInput
from server.services.roster_import import (
    RosterWorkbookError,
    parse_l2_on_call_csv,
    parse_l2_on_call_workbook,
    parse_roster_csv,
    parse_roster_workbook,
)
from openpyxl import Workbook


def roster_csv(month_year: tuple[int, int] = (2026, 10), team_label: str = "") -> bytes:
    year, month = month_year
    day_count = 31 if month in {1, 3, 5, 7, 8, 10, 12} else 30 if month in {4, 6, 9, 11} else 28
    if month == 2 and year % 4 == 0:
        day_count = 29
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["FO Name", "Location", "", *[date(year, month, day).isoformat() for day in range(1, day_count + 1)]])
    writer.writerow(["", "", "Domain"])
    writer.writerow(["Operator One", "Addis Ababa", team_label, *(["M"] * day_count)])
    return output.getvalue().encode("utf-8")


class LoginRateLimiterTests(unittest.TestCase):
    def test_account_limit_returns_retry_after(self):
        limiter = LoginRateLimiter()
        for _ in range(10):
            self.assertEqual(limiter.retry_after("192.0.2.10", "admin"), 0)
            limiter.record_failure("192.0.2.10", "admin")
        self.assertGreater(limiter.retry_after("192.0.2.10", "admin"), 0)

    def test_success_clears_account_counter(self):
        limiter = LoginRateLimiter()
        for _ in range(10):
            limiter.record_failure("192.0.2.10", "admin")
        limiter.record_success("192.0.2.10", "admin")
        self.assertEqual(limiter.retry_after("192.0.2.10", "admin"), 0)

    def test_address_limit_applies_across_usernames(self):
        limiter = LoginRateLimiter()
        for index in range(60):
            username = f"user-{index}"
            self.assertEqual(limiter.retry_after("192.0.2.20", username), 0)
            limiter.record_failure("192.0.2.20", username)
        self.assertGreater(limiter.retry_after("192.0.2.20", "another-user"), 0)


class LoginHandlerTests(unittest.TestCase):
    class FakeDatabase:
        def __init__(self, user):
            self.user = user

        def scalar(self, _query):
            return self.user

    @staticmethod
    def request(address="192.0.2.30"):
        return Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [],
            "client": (address, 43210),
            "server": ("localhost", 8000),
        })

    @staticmethod
    def user(password):
        return User(
            id=10,
            username="admin",
            email="admin@example.com",
            full_name="Portal Admin",
            password_hash=hash_password(password),
            role=UserRole.admin,
            is_active=True,
            can_edit_content=False,
            can_upload_roster=False,
            avatar_key="default",
            auth_version=0,
            created_at=datetime.now(timezone.utc),
        )

    def test_successful_login_sets_http_only_session_cookie(self):
        password = "LongStrongPassword123!"
        limiter = LoginRateLimiter()
        with patch.object(auth_controller, "login_rate_limiter", limiter):
            response = auth_controller.login(
                LoginInput(username=" Admin ", password=password),
                self.request(),
                self.FakeDatabase(self.user(password)),
            )
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].casefold()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("max-age=1800", cookie)

    def test_unknown_and_wrong_password_accounts_use_same_auth_error(self):
        limiter = LoginRateLimiter()
        user = self.user("AnotherStrongPassword123!")
        cases = (
            (self.FakeDatabase(None), "unknown"),
            (self.FakeDatabase(user), "admin"),
        )
        with patch.object(auth_controller, "login_rate_limiter", limiter):
            for database, username in cases:
                with self.subTest(username=username):
                    with self.assertRaises(HTTPException) as caught:
                        auth_controller.login(
                            LoginInput(username=username, password="WrongPassword123!"),
                            self.request(),
                            database,
                        )
                    self.assertEqual(caught.exception.status_code, 401)
                    self.assertEqual(caught.exception.detail, "Invalid username or password")


class PermissionTests(unittest.TestCase):
    @staticmethod
    def user(role: UserRole, **overrides) -> User:
        values = {
            "id": 1,
            "username": "operator",
            "email": "operator@example.com",
            "full_name": "Portal Operator",
            "password_hash": "unused",
            "role": role,
            "can_edit_content": False,
            "can_upload_roster": False,
        }
        values.update(overrides)
        return User(**values)

    def test_operator_content_and_roster_permissions_are_individually_gated(self):
        operator = self.user(UserRole.operator)
        self.assertFalse(allowed(operator, Permission.edit_process_articles))
        self.assertFalse(allowed(operator, Permission.upload_roster))
        operator.can_edit_content = True
        self.assertTrue(allowed(operator, Permission.edit_process_articles))
        self.assertFalse(allowed(operator, Permission.upload_roster))
        operator.can_upload_roster = True
        self.assertTrue(allowed(operator, Permission.upload_roster))

    def test_guest_cannot_submit_handovers_and_admin_can_manage_users(self):
        self.assertFalse(allowed(self.user(UserRole.guest), Permission.submit_handovers))
        self.assertTrue(allowed(self.user(UserRole.admin), Permission.manage_users))


class RosterImportTests(unittest.TestCase):
    def test_csv_front_office_month_parses_assignments(self):
        parsed = parse_roster_csv(roster_csv(), "October 2026.csv")
        self.assertEqual(parsed["month_label"], "October 2026")
        self.assertEqual(parsed["members"][0]["name"], "Operator One")
        self.assertEqual(len(parsed["assignments"]), 31)
        self.assertEqual(parsed["assignments"][0]["shift_name"], "morning")

    def test_csv_roster_rejects_team_labels_missing_from_registry(self):
        with self.assertRaisesRegex(
            RosterWorkbookError,
            "row 3: unknown team label 'Powerful'. Add this label in Admin > Team mappings",
        ):
            parse_roster_csv(
                roster_csv(team_label="Powerful"),
                "October 2026.csv",
                allowed_team_labels={"Power Gen", "Transmission"},
            )

    def test_csv_roster_matches_registered_labels_case_insensitively(self):
        parsed = parse_roster_csv(
            roster_csv(team_label="power gen"),
            "October 2026.csv",
            allowed_team_labels={"Power Gen"},
        )
        self.assertEqual(parsed["members"][0]["team"], "power gen")

    def test_invalid_csv_roster_is_a_validation_error(self):
        with self.assertRaises(RosterWorkbookError):
            parse_roster_csv(b"name,location\nOperator One,Addis Ababa\n", "roster.csv")

    def test_l2_csv_supports_grouped_blank_domain_cells(self):
        content = (
            "Domain,Tier,Name,Phone,Email\n"
            "RAN,Primary L2,Dawit Tadele,+251700000001,dawit@example.com\n"
            ",Secondary L2,Yalfal Tadesse,+251700000002,yalfal@example.com\n"
        ).encode("utf-8")
        parsed = parse_l2_on_call_csv(content)
        self.assertEqual(len(parsed["records"]), 2)
        self.assertEqual(parsed["records"][1]["department"], "ran")
        self.assertEqual(parsed["records"][1]["email"], "yalfal@example.com")

    def test_l2_xlsx_parses_standard_contact_sheet(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "On Call"
        sheet.append(["Domain", "Tier", "Name", "Phone", "Email"])
        sheet.append(["Power", "Primary L2", "Bisrat Awaye", "+251700000003", "bisrat@example.com"])
        content = io.BytesIO()
        workbook.save(content)
        parsed = parse_l2_on_call_workbook(content.getvalue())
        self.assertEqual(parsed["records"][0]["department"], "power")
        self.assertEqual(parsed["records"][0]["tier"], "Primary L2")

    def test_l2_csv_rejects_unknown_domain(self):
        content = b"Domain,Name\nUnknown Network,Operator One\n"
        with self.assertRaises(RosterWorkbookError):
            parse_l2_on_call_csv(content)

    def test_l2_csv_normalizes_legacy_core_domain_names(self):
        content = (
            "Domain,Name\n"
            "PSCore & SDM,PS Core Operator\n"
            "CS Core & VoLTE,CS Core Operator\n"
        ).encode("utf-8")
        parsed = parse_l2_on_call_csv(content)
        self.assertEqual(
            [record["department"] for record in parsed["records"]],
            ["ps_core_sdm", "cs_core_volte"],
        )

    def test_invalid_xlsx_archive_returns_validation_error(self):
        with self.assertRaises(RosterWorkbookError):
            parse_roster_workbook(b"PK not a workbook")

    def test_l2_csv_row_limit_is_enforced(self):
        rows = ["Domain,Name", *[f"RAN,Operator {index}" for index in range(20_001)]]
        with self.assertRaisesRegex(RosterWorkbookError, "20,000 row limit"):
            parse_l2_on_call_csv("\n".join(rows).encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
