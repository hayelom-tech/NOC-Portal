import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time as day_time
from io import BytesIO
from threading import Barrier

from openpyxl import Workbook
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from server.database import SessionLocal
from server.database import Base
from server.models import (
    AuditLog,
    Handover,
    KnowledgeArticle,
    KnowledgeDomain,
    L2Roster,
    RosterAssignment,
    RosterMember,
    RosterTeam,
    Shift,
    ShiftName,
    User,
    UserRole,
    utc_now,
)
from server.services.security import hash_password


BASE_URL = "http://127.0.0.1:18765"
ADMIN_USERNAME = os.environ["INITIAL_ADMIN_USERNAME"]
ADMIN_PASSWORD = os.environ["INITIAL_ADMIN_PASSWORD"]


def post_file_csv(
    assignment_for_first_day: str,
    email: str = "operator@integration.invalid",
    team_label: str = "Power",
) -> bytes:
    import csv
    import io
    from datetime import date

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    days = [date(2026, 10, day).isoformat() for day in range(1, 32)]
    writer.writerow(["FO Name", "Location", "", *days, "Email"])
    writer.writerow(["", "", "Domain"])
    shifts = [assignment_for_first_day, *(["M"] * 30)]
    writer.writerow(["Roster Operator", "Addis Ababa", team_label, *shifts, email])
    return output.getvalue().encode("utf-8")


class PortalHttpFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This suite only runs against its dedicated integration database.
        # Keep the bootstrap admin, but reset all application fixtures so the
        # same Compose command can be run repeatedly without dropping volumes.
        with SessionLocal() as db:
            table_names = [table.name for table in Base.metadata.sorted_tables if table.name != "users"]
            quoted_tables = ", ".join(f'"{name}"' for name in table_names)
            db.execute(text(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE"))
            db.query(User).filter(User.username != ADMIN_USERNAME).delete(synchronize_session=False)
            db.commit()

        cls.server_log = tempfile.TemporaryFile(mode="w+b")
        cls.server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "18765", "--no-access-log"],
            env=os.environ.copy(),
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if cls.server_process.poll() is not None:
                raise RuntimeError(cls._server_output())
            try:
                with urllib.request.urlopen(f"{BASE_URL}/healthz", timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
        else:
            cls.server_process.terminate()
            raise RuntimeError("Test API server did not become ready.\n" + cls._server_output())

        cls.users = {}
        with SessionLocal() as db:
            admin = db.query(User).filter_by(username=ADMIN_USERNAME).one()
            cls.users["admin"] = admin.id
            operator = User(
                username="integration_operator",
                email="operator@integration.invalid",
                full_name="Integration Operator",
                password_hash=hash_password("IntegrationOperator123!"),
                role=UserRole.operator,
                can_edit_content=True,
                can_upload_roster=False,
            )
            limited_operator = User(
                username="limited_operator",
                email="limited-operator@integration.invalid",
                full_name="Limited Operator",
                password_hash=hash_password("LimitedOperator123!"),
                role=UserRole.operator,
            )
            roster_operator = User(
                username="roster_operator",
                email="roster-operator@integration.invalid",
                full_name="Roster Operator",
                password_hash=hash_password("RosterOperator123!"),
                role=UserRole.operator,
                can_upload_roster=True,
            )
            guest = User(
                username="integration_guest",
                email="guest@integration.invalid",
                full_name="Integration Guest",
                password_hash=hash_password("IntegrationGuest123!"),
                role=UserRole.guest,
            )
            power_user = User(
                username="power_recipient",
                email="power@integration.invalid",
                full_name="Power Recipient",
                password_hash=hash_password("PowerRecipient123!"),
                role=UserRole.operator,
            )
            tx_user = User(
                username="tx_recipient",
                email="tx@integration.invalid",
                full_name="TX Recipient",
                password_hash=hash_password("TransmissionRecipient123!"),
                role=UserRole.operator,
            )
            db.add_all([operator, limited_operator, roster_operator, guest, power_user, tx_user])
            db.flush()
            power_team = RosterTeam(name="Power", challenge_domain="power")
            power_gen_team = RosterTeam(name="Power Gen", challenge_domain="power")
            tx_team = RosterTeam(name="Transmission", challenge_domain="tx")
            db.add_all([power_team, power_gen_team, tx_team])
            db.flush()
            cls.users.update({
                "operator": operator.id,
                "limited_operator": limited_operator.id,
                "roster_operator": roster_operator.id,
                "guest": guest.id,
                "power": power_user.id,
                "tx": tx_user.id,
            })

            power_shift = Shift(
                shift_date=date(2026, 10, 15),
                shift_name=ShiftName.morning,
                start_time=day_time(6),
                end_time=day_time(14),
                uploaded_by_id=admin.id,
            )
            tx_shift = Shift(
                shift_date=date(2026, 10, 15),
                shift_name=ShiftName.night,
                start_time=day_time(22),
                end_time=day_time(6),
                uploaded_by_id=admin.id,
            )
            shift_without_handover = Shift(
                shift_date=date(2026, 10, 17),
                shift_name=ShiftName.afternoon,
                start_time=day_time(14),
                end_time=day_time(22),
                uploaded_by_id=admin.id,
            )
            db.add_all([power_shift, tx_shift, shift_without_handover])
            db.flush()

            power_member = RosterMember(
                name="Power Recipient",
                roster_team_id=power_gen_team.id,
                user_id=power_user.id,
            )
            tx_member = RosterMember(
                name="TX Recipient",
                roster_team_id=tx_team.id,
                user_id=tx_user.id,
            )
            db.add_all([power_member, tx_member])
            db.flush()
            db.add_all([
                RosterAssignment(
                    member_id=power_member.id,
                    assignment_date=date(2026, 10, 15),
                    shift_code="A",
                    shift_name=ShiftName.afternoon,
                ),
                RosterAssignment(
                    member_id=tx_member.id,
                    assignment_date=date(2026, 10, 16),
                    shift_code="M",
                    shift_name=ShiftName.morning,
                ),
            ])
            db.add_all([
                AuditLog(
                    actor_user_id=operator.id,
                    action="integration.operator_action",
                    entity_type="test",
                    entity_id="operator",
                ),
                AuditLog(
                    actor_user_id=admin.id,
                    action="integration.admin_action",
                    entity_type="test",
                    entity_id="admin",
                ),
            ])
            db.add_all([
                Handover(
                    shift_id=power_shift.id,
                    next_shift_name=ShiftName.afternoon,
                    operational_challenges=True,
                    challenge_domain="power",
                    update_for_next_shift="Power challenge details",
                    active_change_requests="CR-1001",
                    planned_maintenance="Power maintenance details",
                    active_field_teams="Team alpha",
                    major_incidents="2",
                    resolved_major_incidents="1",
                    alarms_pending_resolution="3",
                    closed_trouble_tickets=4,
                    archived_handover_index="archive-power",
                    created_by_id=admin.id,
                    updated_at=utc_now(),
                ),
                Handover(
                    shift_id=tx_shift.id,
                    next_shift_name=ShiftName.morning,
                    operational_challenges=True,
                    challenge_domain="tx",
                    update_for_next_shift="Transmission challenge details",
                    active_change_requests="CR-2002",
                    planned_maintenance="Transmission maintenance details",
                    created_by_id=admin.id,
                    updated_at=utc_now(),
                ),
            ])
            db.commit()
            cls.power_shift_id = power_shift.id
            cls.tx_shift_id = tx_shift.id
            cls.shift_without_handover_id = shift_without_handover.id

    @classmethod
    def tearDownClass(cls):
        cls.server_process.terminate()
        try:
            cls.server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server_process.kill()
            cls.server_process.wait(timeout=5)
        cls.server_log.close()

    @classmethod
    def _server_output(cls):
        cls.server_log.flush()
        cls.server_log.seek(0)
        return cls.server_log.read().decode("utf-8", errors="replace")

    @staticmethod
    def request_json(opener, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=10) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            body = error.read()
            if not body:
                return error.code, None
            try:
                return error.code, json.loads(body)
            except json.JSONDecodeError:
                return error.code, body.decode("utf-8", errors="replace")

    @staticmethod
    def request_raw(opener, path):
        request = urllib.request.Request(BASE_URL + path, method="GET")
        try:
            with opener.open(request, timeout=10) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    @classmethod
    def client_for(cls, username, password):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        status, result = cls.request_json(opener, "POST", "/api/v1/auth/login", {
            "username": username,
            "password": password,
        })
        if status != 200:
            raise AssertionError(f"Login for {username} failed ({status}): {result}")
        return opener

    @classmethod
    def client(cls, role):
        credentials = {
            "admin": (ADMIN_USERNAME, ADMIN_PASSWORD),
            "operator": ("integration_operator", "IntegrationOperator123!"),
            "limited_operator": ("limited_operator", "LimitedOperator123!"),
            "roster_operator": ("roster_operator", "RosterOperator123!"),
            "guest": ("integration_guest", "IntegrationGuest123!"),
            "power": ("power_recipient", "PowerRecipient123!"),
            "tx": ("tx_recipient", "TransmissionRecipient123!"),
        }
        return cls.client_for(*credentials[role])

    @staticmethod
    def multipart_file_request(opener, path, filename, content):
        boundary = "----noc-test-" + uuid.uuid4().hex
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if filename.casefold().endswith(".xlsx")
            else "text/csv"
        )
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("ascii") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = urllib.request.Request(
            BASE_URL + path,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            body = error.read()
            return error.code, json.loads(body) if body else None

    def test_operator_post_notifies_admin_and_requires_approval(self):
        operator = self.client("operator")
        guest = self.client("guest")
        admin = self.client("admin")
        payload = {
            "domain": "power",
            "issue_title": "Integration approval flow",
            "symptoms": "A test symptom",
            "root_cause": "A test cause",
            "troubleshooting_steps": "Check the integration fixture",
            "resolution": "Apply the test resolution",
            "reference_link": None,
            "is_active": True,
        }
        status, article = self.request_json(operator, "POST", "/api/v1/knowledge-hub", payload)
        self.assertEqual(status, 201)
        self.assertEqual(article["approval_status"], "pending")
        self.assertFalse(article["is_active"])

        status, pending = self.request_json(guest, "GET", "/api/v1/knowledge-hub/pending")
        self.assertEqual(status, 403)
        status, notifications = self.request_json(admin, "GET", "/api/v1/notifications")
        self.assertEqual(status, 200)
        self.assertTrue(any(row["article_id"] == article["id"] for row in notifications))
        status, guest_approval = self.request_json(
            guest, "POST", f"/api/v1/knowledge-hub/{article['id']}/approve"
        )
        self.assertEqual(status, 403)

        status, approved = self.request_json(
            admin, "POST", f"/api/v1/knowledge-hub/{article['id']}/approve"
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved["approval_status"], "approved")
        self.assertTrue(approved["is_active"])
        status, public_articles = self.request_json(guest, "GET", "/api/v1/knowledge-hub")
        self.assertEqual(status, 200)
        self.assertTrue(any(row["id"] == article["id"] for row in public_articles))

    def test_challenge_details_are_visible_only_to_assigned_domain_recipient(self):
        power = self.client("power")
        tx = self.client("tx")
        guest = self.client("guest")
        admin = self.client("admin")

        status, power_handover = self.request_json(
            power, "GET", f"/api/v1/shifts/{self.power_shift_id}/handover"
        )
        self.assertEqual(status, 200)
        self.assertEqual(power_handover["update_for_next_shift"], "Power challenge details")
        self.assertEqual(power_handover["challenge_domain"], "power")

        for client in (tx, guest):
            status, redacted = self.request_json(
                client, "GET", f"/api/v1/shifts/{self.power_shift_id}/handover"
            )
            self.assertEqual(status, 200)
            self.assertIsNone(redacted["challenge_domain"])
            self.assertEqual(redacted["update_for_next_shift"], "")
            self.assertEqual(redacted["active_change_requests"], "")
            self.assertEqual(redacted["planned_maintenance"], "")
            self.assertEqual(redacted["active_field_teams"], "")
            self.assertEqual(redacted["major_incidents"], "0")
            self.assertEqual(redacted["resolved_major_incidents"], "0")
            self.assertEqual(redacted["alarms_pending_resolution"], "0")
            self.assertEqual(redacted["closed_trouble_tickets"], 0)
            self.assertIsNone(redacted["archived_handover_index"])
            self.assertEqual(redacted["field_teams"], [])

        tampering_payload = {
            "expected_updated_at": redacted["updated_at"],
            "next_shift_name": "afternoon",
            "operational_challenges": True,
            "challenge_domain": "power",
            "update_for_next_shift": "Unauthorized change",
            "active_change_requests": "CR-UNAUTHORIZED",
            "planned_maintenance": "Unauthorized maintenance",
            "active_field_teams": "Unauthorized team",
            "major_incidents": "50",
            "resolved_major_incidents": "50",
            "alarms_pending_resolution": "50",
            "closed_trouble_tickets": 50,
            "archived_handover_index": "unauthorized-archive",
            "regions": [
                {"region_name": name}
                for name in ("East 1", "East 2", "West", "North West", "North East", "North", "Afar")
            ],
            "field_teams": [{"site_id": "999", "name": "Unauthorized team"}],
        }
        status, tampering_result = self.request_json(
            tx,
            "PUT",
            f"/api/v1/shifts/{self.power_shift_id}/handover",
            tampering_payload,
        )
        self.assertEqual(status, 200, tampering_result)

        status, admin_handover = self.request_json(
            admin, "GET", f"/api/v1/shifts/{self.power_shift_id}/handover"
        )
        self.assertEqual(status, 200)
        self.assertEqual(admin_handover["update_for_next_shift"], "Power challenge details")
        self.assertEqual(admin_handover["active_field_teams"], "Team alpha")
        self.assertEqual(admin_handover["major_incidents"], "2")
        self.assertEqual(admin_handover["resolved_major_incidents"], "1")
        self.assertEqual(admin_handover["alarms_pending_resolution"], "3")
        self.assertEqual(admin_handover["closed_trouble_tickets"], 4)
        self.assertEqual(admin_handover["archived_handover_index"], "archive-power")
        self.assertEqual(admin_handover["field_teams"], [])

        status, night_tx_handover = self.request_json(
            tx, "GET", f"/api/v1/shifts/{self.tx_shift_id}/handover"
        )
        self.assertEqual(status, 200)
        self.assertEqual(night_tx_handover["update_for_next_shift"], "Transmission challenge details")

    def test_assigned_roster_member_without_team_does_not_receive_domain_challenge(self):
        with SessionLocal() as db:
            null_team_user = User(
                username="null_team_recipient",
                email="null-team@integration.invalid",
                full_name="Unmapped Team Recipient",
                password_hash=hash_password("NullTeamRecipient123!"),
                role=UserRole.operator,
            )
            db.add(null_team_user)
            db.flush()
            member = RosterMember(
                name="Unmapped Team Recipient",
                roster_team_id=None,
                user_id=null_team_user.id,
            )
            db.add(member)
            db.flush()
            db.add(RosterAssignment(
                member_id=member.id,
                assignment_date=date(2026, 10, 15),
                shift_code="A",
                shift_name=ShiftName.afternoon,
            ))
            db.commit()

        response_status, handover = self.request_json(
            self.client_for("null_team_recipient", "NullTeamRecipient123!"),
            "GET",
            f"/api/v1/shifts/{self.power_shift_id}/handover",
        )
        self.assertEqual(response_status, 200, handover)
        self.assertIsNone(handover["challenge_domain"])
        self.assertEqual(handover["update_for_next_shift"], "")

    def test_guest_cannot_access_admin_user_management(self):
        guest = self.client("guest")
        status, response = self.request_json(guest, "GET", "/api/v1/users")
        self.assertEqual(status, 403)

    def test_user_management_and_content_permissions_follow_role_flags(self):
        guest = self.client("guest")
        operator = self.client("operator")
        limited_operator = self.client("limited_operator")
        admin = self.client("admin")

        user_payload = {
            "username": "permission_created_user",
            "email": "permission-created@integration.invalid",
            "full_name": "Permission Test User",
            "password": "PermissionTest123!",
            "role": "guest",
        }
        for client, method, path, payload in (
            (guest, "POST", "/api/v1/users", user_payload),
            (operator, "GET", "/api/v1/users", None),
            (limited_operator, "PATCH", f"/api/v1/users/{self.users['guest']}", {"is_active": False}),
            (operator, "DELETE", f"/api/v1/users/{self.users['guest']}", None),
        ):
            status, response = self.request_json(client, method, path, payload)
            self.assertEqual(status, 403, (method, path, response))

        status, users = self.request_json(admin, "GET", "/api/v1/users")
        self.assertEqual(status, 200)
        status, created_user = self.request_json(admin, "POST", "/api/v1/users", user_payload)
        self.assertEqual(status, 201, created_user)
        status, updated_user = self.request_json(
            admin,
            "PATCH",
            f"/api/v1/users/{created_user['id']}",
            {"full_name": "Updated Permission Test User"},
        )
        self.assertEqual(status, 200, updated_user)
        status, _ = self.request_json(admin, "DELETE", f"/api/v1/users/{created_user['id']}")
        self.assertEqual(status, 204)

        process_payload = {
            "category": "Integration",
            "title": "Permission-gated process",
            "description": "Test fixture",
            "steps": "Step one",
            "is_active": True,
        }
        status, response = self.request_json(limited_operator, "POST", "/api/v1/process", process_payload)
        self.assertEqual(status, 403, response)
        status, response = self.request_json(limited_operator, "POST", "/api/v1/knowledge-hub", {
            "domain": "power",
            "issue_title": "Unauthorized post",
            "symptoms": "Test",
            "root_cause": "Test",
            "troubleshooting_steps": "Test",
            "resolution": "Test",
        })
        self.assertEqual(status, 403, response)
        status, response = self.request_json(guest, "POST", "/api/v1/knowledge-hub", {
            "domain": "power",
            "issue_title": "Guest post",
            "symptoms": "Test",
            "root_cause": "Test",
            "troubleshooting_steps": "Test",
            "resolution": "Test",
        })
        self.assertEqual(status, 403, response)

        status, created_process = self.request_json(operator, "POST", "/api/v1/process", process_payload)
        self.assertEqual(status, 201, created_process)
        status, created_process = self.request_json(admin, "POST", "/api/v1/process", {
            **process_payload,
            "title": "Admin-created process",
        })
        self.assertEqual(status, 201, created_process)
        status, admin_article = self.request_json(admin, "POST", "/api/v1/knowledge-hub", {
            "domain": "power",
            "issue_title": "Admin-approved post",
            "symptoms": "Test",
            "root_cause": "Test",
            "troubleshooting_steps": "Test",
            "resolution": "Test",
        })
        self.assertEqual(status, 201, admin_article)
        self.assertEqual(admin_article["approval_status"], "approved")

    def test_roster_upload_permissions_allow_only_admin_or_authorized_operator(self):
        guest = self.client("guest")
        limited_operator = self.client("limited_operator")
        roster_operator = self.client("roster_operator")
        admin = self.client("admin")
        roster_content = post_file_csv("A", "roster-operator@integration.invalid")

        for client, path in (
            (guest, "/api/v1/uploads/template"),
            (limited_operator, "/api/v1/uploads/template"),
            (limited_operator, "/api/v1/uploads/l2-template"),
            (roster_operator, "/api/v1/uploads"),
        ):
            status, response = self.request_json(client, "GET", path)
            self.assertEqual(status, 403, (path, response))

        status, result = self.multipart_file_request(
            limited_operator,
            "/api/v1/uploads/excel",
            "Unauthorized roster.csv",
            roster_content,
        )
        self.assertEqual(status, 403, result)
        status, result = self.multipart_file_request(
            roster_operator,
            "/api/v1/uploads/excel",
            "Authorized roster.csv",
            roster_content,
        )
        self.assertEqual(status, 201, result)
        status, _, workbook = self.request_raw(roster_operator, "/api/v1/uploads/template")
        self.assertEqual(status, 200)
        self.assertTrue(workbook.startswith(b"PK"))
        status, _, workbook = self.request_raw(admin, "/api/v1/uploads/l2-template")
        self.assertEqual(status, 200)
        self.assertTrue(workbook.startswith(b"PK"))
        status, logs = self.request_json(admin, "GET", "/api/v1/uploads")
        self.assertEqual(status, 200)
        self.assertTrue(logs)

    def test_roster_upload_rejects_unregistered_team_label(self):
        status, result = self.multipart_file_request(
            self.client("admin"),
            "/api/v1/uploads/excel",
            "Unknown team.csv",
            post_file_csv("A", team_label="Powerful"),
        )
        self.assertEqual(status, 422, result)
        self.assertIn("unknown team label 'Powerful'", result["detail"])
        self.assertIn("Admin > Team mappings", result["detail"])

    def test_admin_can_manage_roster_team_mappings(self):
        admin = self.client("admin")
        status, teams = self.request_json(admin, "GET", "/api/v1/roster-teams")
        self.assertEqual(status, 200, teams)
        power_team = next(team for team in teams if team["name"] == "Power")
        self.assertEqual(power_team["challenge_domain"], "power")

        status, result = self.request_json(
            admin,
            "POST",
            "/api/v1/roster-teams",
            {"name": "Auxiliary Network", "challenge_domain": None},
        )
        self.assertEqual(status, 201, result)
        self.assertIsNone(result["challenge_domain"])
        team_id = result["id"]

        status, result = self.request_json(
            admin,
            "PATCH",
            f"/api/v1/roster-teams/{team_id}",
            {"challenge_domain": "tx"},
        )
        self.assertEqual(status, 200, result)
        self.assertEqual(result["challenge_domain"], "tx")

        status, result = self.request_json(
            self.client("roster_operator"),
            "GET",
            "/api/v1/roster-teams",
        )
        self.assertEqual(status, 403, result)

    def test_roster_team_domain_is_enforced_by_database_constraint(self):
        with SessionLocal() as db:
            with self.assertRaises(IntegrityError):
                db.execute(text("""
                    INSERT INTO roster_teams (name, challenge_domain)
                    VALUES ('Invalid challenge team', 'powerful')
                """))
            db.rollback()

    def test_roster_member_requires_a_registered_team_foreign_key(self):
        with SessionLocal() as db:
            with self.assertRaises(IntegrityError):
                db.execute(text("""
                    INSERT INTO roster_members (name, roster_team_id, created_at)
                    VALUES ('Invalid roster team foreign key', -1, CURRENT_TIMESTAMP)
                """))
            db.rollback()

    def test_process_documents_are_admin_managed_and_authenticated_users_can_read(self):
        guest = self.client("guest")
        operator = self.client("operator")
        admin = self.client("admin")
        content = b"Integration process document."

        for client in (guest, operator):
            status, response = self.multipart_file_request(
                client,
                "/api/v1/process-documents",
                "Process permission.txt",
                content,
            )
            self.assertEqual(status, 403, response)

        status, document = self.multipart_file_request(
            admin,
            "/api/v1/process-documents",
            "Process permission.txt",
            content,
        )
        self.assertEqual(status, 201, document)
        document_id = document["id"]
        status, documents = self.request_json(guest, "GET", "/api/v1/process-documents")
        self.assertEqual(status, 200)
        self.assertTrue(any(row["id"] == document_id for row in documents))
        status, headers, view = self.request_raw(guest, f"/api/v1/process-documents/{document_id}/view")
        self.assertEqual(status, 200)
        self.assertEqual(view, content)
        status, response = self.request_json(guest, "DELETE", f"/api/v1/process-documents/{document_id}")
        self.assertEqual(status, 403, response)
        status, response = self.request_json(admin, "DELETE", f"/api/v1/process-documents/{document_id}")
        self.assertEqual(status, 200, response)

    def test_database_constraints_reject_unknown_l2_domain_and_approval_status(self):
        with SessionLocal() as db:
            db.add(L2Roster(
                department="unknown_domain",
                engineer_name="Invalid Domain Contact",
            ))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(KnowledgeArticle(
                domain=KnowledgeDomain.power,
                issue_title="Invalid approval status",
                symptoms="Test symptom",
                root_cause="Test cause",
                troubleshooting_steps="Test steps",
                resolution="Test resolution",
                approval_status="published",
                created_by_id=self.users["admin"],
            ))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_l2_domain_migration_stops_on_normalization_collision(self):
        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "server/alembic.ini",
                "downgrade",
                "0012_roster_member_user_email",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(downgrade.returncode, 0, downgrade.stderr)
        try:
            with SessionLocal() as db:
                db.execute(text("""
                    INSERT INTO l2_roster
                        (department, week, engineer_name, updated_at)
                    VALUES
                        ('Transmission', 42, 'Migration collision A', CURRENT_TIMESTAMP),
                        ('tx', 42, 'Migration collision B', CURRENT_TIMESTAMP)
                """))
                db.commit()

            upgrade = subprocess.run(
                [sys.executable, "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"],
                env=os.environ.copy(),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(upgrade.returncode, 0)
            self.assertIn("multiple rows would share", upgrade.stderr)
        finally:
            with SessionLocal() as db:
                db.execute(text(
                    "DELETE FROM l2_roster WHERE engineer_name LIKE 'Migration collision %'"
                ))
                db.commit()
            upgrade = subprocess.run(
                [sys.executable, "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"],
                env=os.environ.copy(),
                capture_output=True,
                text=True,
            )
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
            with SessionLocal() as db:
                power_member = db.query(RosterMember).filter_by(name="Power Recipient").one()
                tx_member = db.query(RosterMember).filter_by(name="TX Recipient").one()
                self.assertEqual(power_member.roster_team.challenge_domain, "power")
                self.assertEqual(tx_member.roster_team.challenge_domain, "tx")

    def test_roster_team_migration_rolls_back_and_can_be_reapplied(self):
        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "server/alembic.ini",
                "downgrade",
                "0013_domain_and_approval_checks",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(downgrade.returncode, 0, downgrade.stderr)

        with SessionLocal() as db:
            db.execute(text("""
                CREATE TABLE roster_teams (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(40) NOT NULL CONSTRAINT uq_roster_teams_name UNIQUE,
                    challenge_domain VARCHAR(20)
                )
            """))
            db.execute(text("""
                INSERT INTO roster_teams (name, challenge_domain)
                VALUES ('Invalid partial registry row', 'not-a-domain')
            """))
            db.commit()

        failed_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "server/alembic.ini",
                "upgrade",
                "0014_roster_team_registry",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(failed_upgrade.returncode, 0)
        self.assertIn("ck_roster_teams_challenge_domain", failed_upgrade.stderr)

        with SessionLocal() as db:
            version = db.scalar(text("SELECT version_num FROM alembic_version"))
            member_columns = {
                column["name"] for column in inspect(db.bind).get_columns("roster_members")
            }
            check_names = {
                check["name"]
                for check in inspect(db.bind).get_check_constraints("roster_teams")
            }
            self.assertEqual(version, "0013_domain_and_approval_checks")
            self.assertIn("team", member_columns)
            self.assertNotIn("roster_team_id", member_columns)
            self.assertNotIn("ck_roster_teams_challenge_domain", check_names)
            db.execute(text("DELETE FROM roster_teams WHERE name = 'Invalid partial registry row'"))
            db.commit()

        successful_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "server/alembic.ini",
                "upgrade",
                "0014_roster_team_registry",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(successful_upgrade.returncode, 0, successful_upgrade.stderr)

        with SessionLocal() as db:
            power_member = db.query(RosterMember).filter_by(name="Power Recipient").one()
            tx_member = db.query(RosterMember).filter_by(name="TX Recipient").one()
            power_team_id = power_member.roster_team_id
            tx_team_id = tx_member.roster_team_id
            team_count = db.query(RosterTeam).count()
            self.assertEqual(power_member.roster_team.challenge_domain, "power")
            self.assertEqual(tx_member.roster_team.challenge_domain, "tx")
            db.execute(text("DELETE FROM roster_teams WHERE name = 'Power Domain'"))
            self.assertIsNone(
                db.query(RosterTeam.id).filter_by(name="Power Domain").scalar()
            )
            db.execute(text(
                "UPDATE alembic_version SET version_num = '0013_domain_and_approval_checks'"
            ))
            db.commit()

        repeated_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "server/alembic.ini",
                "upgrade",
                "0014_roster_team_registry",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(repeated_upgrade.returncode, 0, repeated_upgrade.stderr)
        with SessionLocal() as db:
            self.assertEqual(db.query(RosterTeam).count(), team_count)
            restored_alias = db.query(RosterTeam).filter_by(name="Power Domain").one()
            self.assertEqual(restored_alias.challenge_domain, "power")
            self.assertEqual(
                db.query(RosterMember).filter_by(name="Power Recipient").one().roster_team_id,
                power_team_id,
            )
            self.assertEqual(
                db.query(RosterMember).filter_by(name="TX Recipient").one().roster_team_id,
                tx_team_id,
            )
            self.assertEqual(
                db.scalar(text("SELECT version_num FROM alembic_version")),
                "0014_roster_team_registry",
            )

    def test_process_document_upload_rejects_corrupt_and_mislabeled_files(self):
        admin = self.client("admin")
        cases = (
            ("Corrupt.pdf", b"not a PDF", 415),
            ("Corrupt.docx", b"PK not a valid Office archive", 415),
            ("Mislabeled.xlsx", b"plain text,not an Excel workbook", 415),
            ("Binary.txt", b"\x00\x01\x02", 415),
        )
        for filename, content, expected_status in cases:
            with self.subTest(filename=filename):
                status, response = self.multipart_file_request(
                    admin, "/api/v1/process-documents", filename, content
                )
                self.assertEqual(status, expected_status, response)

    def test_process_and_knowledge_updates_reject_stale_revisions(self):
        admin_one = self.client("admin")
        admin_two = self.client("admin")
        process_payload = {
            "category": "Integration",
            "title": "Concurrency test process",
            "description": "Process revision test",
            "steps": "Initial steps",
            "is_active": True,
        }
        status, process = self.request_json(admin_one, "POST", "/api/v1/process", process_payload)
        self.assertEqual(status, 201, process)
        self.assertNotIn("expected_updated_at", process)

        missing_revision = dict(process_payload, title="Missing revision")
        status, response = self.request_json(
            admin_one, "PUT", f"/api/v1/process/{process['id']}", missing_revision
        )
        self.assertEqual(status, 428, response)

        barrier = Barrier(2)

        def update_process(client, title):
            payload = {
                **process_payload,
                "title": title,
                "expected_updated_at": process["updated_at"],
            }
            barrier.wait(timeout=5)
            return self.request_json(
                client, "PUT", f"/api/v1/process/{process['id']}", payload
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            process_results = list(pool.map(
                lambda args: update_process(*args),
                ((admin_one, "Process edit A"), (admin_two, "Process edit B")),
            ))
        self.assertEqual(sorted(status for status, _ in process_results), [200, 409], process_results)

        article_payload = {
            "domain": "power",
            "issue_title": "Concurrency test article",
            "symptoms": "Initial symptoms",
            "root_cause": "Initial cause",
            "troubleshooting_steps": "Initial steps",
            "resolution": "Initial resolution",
            "is_active": True,
        }
        status, article = self.request_json(
            admin_one, "POST", "/api/v1/knowledge-hub", article_payload
        )
        self.assertEqual(status, 201, article)
        self.assertNotIn("expected_updated_at", article)

        missing_revision = dict(article_payload, issue_title="Missing revision")
        status, response = self.request_json(
            admin_one,
            "PUT",
            f"/api/v1/knowledge-hub/{article['id']}",
            missing_revision,
        )
        self.assertEqual(status, 428, response)

        barrier = Barrier(2)

        def update_article(client, title):
            payload = {
                **article_payload,
                "issue_title": title,
                "expected_updated_at": article["updated_at"],
            }
            barrier.wait(timeout=5)
            return self.request_json(
                client, "PUT", f"/api/v1/knowledge-hub/{article['id']}", payload
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            article_results = list(pool.map(
                lambda args: update_article(*args),
                ((admin_one, "Article edit A"), (admin_two, "Article edit B")),
            ))
        self.assertEqual(sorted(status for status, _ in article_results), [200, 409], article_results)

    def test_operator_audit_history_is_limited_to_own_actions(self):
        operator = self.client("operator")
        admin = self.client("admin")

        status, operator_logs = self.request_json(operator, "GET", "/api/v1/audit-logs")
        self.assertEqual(status, 200)
        self.assertTrue(operator_logs)
        self.assertTrue(all(row["actor_user_id"] == self.users["operator"] for row in operator_logs))

        status, admin_logs = self.request_json(admin, "GET", "/api/v1/audit-logs")
        self.assertEqual(status, 200)
        actor_ids = {row["actor_user_id"] for row in admin_logs}
        self.assertIn(self.users["operator"], actor_ids)
        self.assertIn(self.users["admin"], actor_ids)

    def test_missing_shift_and_missing_handover_return_not_found(self):
        guest = self.client("guest")
        status, response = self.request_json(guest, "GET", "/api/v1/shifts/999999/handover")
        self.assertEqual(status, 404)
        self.assertEqual(response["detail"], "Shift not found")

        status, response = self.request_json(guest, "GET", "/api/v1/shifts/999998/handover")
        self.assertEqual(status, 404)
        self.assertEqual(response["detail"], "Shift not found")

        status, response = self.request_json(
            guest,
            "GET",
            f"/api/v1/shifts/{self.shift_without_handover_id}/handover",
        )
        self.assertEqual(status, 404)
        self.assertEqual(response["detail"], "No handover has been recorded for this shift")

    def test_invalid_handover_payloads_are_rejected(self):
        operator = self.client("operator")
        invalid_payloads = (
            {"next_shift_name": "afternoon", "regions": []},
            {
                "next_shift_name": "afternoon",
                "regions": [
                    {"region_name": name, "corrective_maintenance_count": 51}
                    for name in ("East 1", "East 2", "West", "North West", "North East", "North", "Afar")
                ],
            },
            {
                "next_shift_name": "afternoon",
                "operational_challenges": True,
                "challenge_domain": "ran",
                "regions": [
                    {"region_name": name}
                    for name in ("East 1", "East 2", "West", "North West", "North East", "North", "Afar")
                ],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                status, response = self.request_json(
                    operator,
                    "PUT",
                    f"/api/v1/shifts/{self.power_shift_id}/handover",
                    payload,
                )
                self.assertEqual(status, 422, response)

    def test_concurrent_acknowledgements_allow_only_one_winner(self):
        operator_one = self.client("operator")
        operator_two = self.client("power")
        barrier = Barrier(2)

        def acknowledge(client):
            barrier.wait(timeout=5)
            return self.request_json(
                client,
                "POST",
                f"/api/v1/shifts/{self.power_shift_id}/handover/acknowledge",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(acknowledge, (operator_one, operator_two)))
        self.assertEqual(sorted(status for status, _ in results), [200, 409], results)

    def test_concurrent_handover_edits_reject_the_stale_writer(self):
        admin_one = self.client("admin")
        admin_two = self.client("admin")
        status, current = self.request_json(
            admin_one,
            "GET",
            f"/api/v1/shifts/{self.power_shift_id}/handover",
        )
        self.assertEqual(status, 200)

        regions = ("East 1", "East 2", "West", "North West", "North East", "North", "Afar")
        base_payload = {
            "expected_updated_at": current["updated_at"],
            "next_shift_name": current["next_shift_name"],
            "update_for_next_shift": current["update_for_next_shift"],
            "operational_challenges": current["operational_challenges"],
            "challenge_domain": current["challenge_domain"],
            "active_change_requests": current["active_change_requests"],
            "planned_maintenance": current["planned_maintenance"],
            "active_field_teams": current["active_field_teams"],
            "major_incidents": "0",
            "resolved_major_incidents": "0",
            "alarms_pending_resolution": "0",
            "closed_trouble_tickets": 0,
            "archived_handover_index": current["archived_handover_index"],
            "regions": [{"region_name": name} for name in regions],
            "field_teams": [],
        }
        payloads = []
        for value in ("Concurrent edit A", "Concurrent edit B"):
            payload = dict(base_payload)
            payload["update_for_next_shift"] = value
            payloads.append(payload)

        # Existing handovers cannot be saved without the revision token.
        missing_revision_payload = dict(base_payload)
        missing_revision_payload.pop("expected_updated_at")
        status, response = self.request_json(
            admin_one,
            "PUT",
            f"/api/v1/shifts/{self.power_shift_id}/handover",
            missing_revision_payload,
        )
        self.assertEqual(status, 428, response)

        barrier = Barrier(2)

        def save(client, payload):
            barrier.wait(timeout=5)
            return self.request_json(
                client,
                "PUT",
                f"/api/v1/shifts/{self.power_shift_id}/handover",
                payload,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (admin_one, admin_two), payloads))
        self.assertEqual(sorted(status for status, _ in results), [200, 409], results)

        status, latest = self.request_json(
            admin_one,
            "GET",
            f"/api/v1/shifts/{self.power_shift_id}/handover",
        )
        self.assertEqual(status, 200)
        self.assertIn(latest["update_for_next_shift"], ("Concurrent edit A", "Concurrent edit B"))

    def test_roster_email_match_routes_power_challenge_to_assignee(self):
        admin = self.client("admin")
        status, result = self.multipart_file_request(
            admin,
            "/api/v1/uploads/excel",
            "October email route.csv",
            post_file_csv("A", "OPERATOR@INTEGRATION.INVALID"),
        )
        self.assertEqual(status, 201, result)

        with SessionLocal() as db:
            source_shift = Shift(
                shift_date=date(2026, 10, 1),
                shift_name=ShiftName.morning,
                start_time=day_time(6),
                end_time=day_time(14),
                uploaded_by_id=self.users["admin"],
            )
            db.add(source_shift)
            db.commit()
            source_shift_id = source_shift.id

        regions = ("East 1", "East 2", "West", "North West", "North East", "North", "Afar")
        payload = {
            "next_shift_name": "afternoon",
            "operational_challenges": True,
            "challenge_domain": "power",
            "update_for_next_shift": "Email matched power challenge",
            "active_change_requests": "CR-EMAIL",
            "planned_maintenance": "Email routing test",
            "regions": [{"region_name": name} for name in regions],
        }
        status, saved = self.request_json(
            self.client("operator"),
            "PUT",
            f"/api/v1/shifts/{source_shift_id}/handover",
            payload,
        )
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["update_for_next_shift"], "Email matched power challenge")

        status, roster = self.request_json(
            self.client("operator"),
            "GET",
            "/api/v1/roster?date=2026-10-01",
        )
        self.assertEqual(status, 200)
        matched = next(row for row in roster if row["member_name"] == "Roster Operator")
        self.assertTrue(matched["assigned_to_current_user"])

    def test_roster_reimport_replaces_assignments_and_matches_member_by_email(self):
        admin = self.client("admin")
        first_status, first_result = self.multipart_file_request(
            admin,
            "/api/v1/uploads/excel",
            "October 2026.csv",
            post_file_csv("M"),
        )
        self.assertEqual(first_status, 201, first_result)
        second_status, second_result = self.multipart_file_request(
            admin,
            "/api/v1/uploads/excel",
            "October 2026.csv",
            post_file_csv("A"),
        )
        self.assertEqual(second_status, 201, second_result)
        self.assertNotEqual(first_result["file_id"], second_result["file_id"])

        operator = self.client("operator")
        status, roster = self.request_json(operator, "GET", "/api/v1/roster?date=2026-10-01")
        self.assertEqual(status, 200)
        assignment = next(row for row in roster if row["member_name"] == "Roster Operator")
        self.assertEqual(assignment["team"], "Power")
        self.assertEqual(assignment["shift_code"], "A")
        self.assertEqual(assignment["shift_name"], "afternoon")
        self.assertTrue(assignment["assigned_to_current_user"])

    def test_xlsx_roster_upload_maps_registered_team_and_returns_team(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "October 2026"
        dates = [date(2026, 10, day) for day in range(1, 32)]
        sheet.append(["FO Name", "Location", "", *dates, "Email"])
        sheet.append(["", "", "Domain", *([None] * len(dates)), ""])
        sheet.append([
            "Excel Roster Operator",
            "Addis Ababa",
            "Power",
            *(["M"] * len(dates)),
            "excel-roster@integration.invalid",
        ])
        content = BytesIO()
        workbook.save(content)

        status, result = self.multipart_file_request(
            self.client("admin"),
            "/api/v1/uploads/excel",
            "Shift Roster October 2026 1 (1).xlsx",
            content.getvalue(),
        )
        self.assertEqual(status, 201, result)

        status, roster = self.request_json(
            self.client("operator"),
            "GET",
            "/api/v1/roster?date=2026-10-01",
        )
        self.assertEqual(status, 200, roster)
        assignment = next(row for row in roster if row["member_name"] == "Excel Roster Operator")
        self.assertEqual(assignment["team"], "Power")


if __name__ == "__main__":
    unittest.main()
