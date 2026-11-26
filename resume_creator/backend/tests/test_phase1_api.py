"""Route and export integration checks using temporary storage and synthetic data."""
from __future__ import annotations

import io
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.database import file_store
from app.routers import auth, resumes
from app.schemas.schemas import CreateResumeRequest
from app.schemas.schemas import AIConfig
from app.security.auth import get_current_user, set_session
from app.utils import llm_providers


class PhaseOneRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nhyapu-craft-tests-")
        root = Path(self.temp.name)
        file_store._root = root / "data"
        settings.generated_dir = str(root / "generated")
        settings.require_email_verification = False
        settings.app_env = "test"
        settings.session_secret = "test-only-session-secret-not-for-production"
        self.user_a = {"id": "user-a", "email": "a@example.test", "name": "Test A", "session_version": 0, "email_verified": True}
        self.user_b = {"id": "user-b", "email": "b@example.test", "name": "Test B", "session_version": 0, "email_verified": True}
        file_store.save_record("users", self.user_a)
        file_store.save_record("users", self.user_b)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def payload(title="Test Resume"):
        return CreateResumeRequest.model_validate({
            "file_name": title,
            "target_role": "Software Developer",
            "template_name": "developer",
            "layout_id": "technical-developer",
            "page_size": "a4",
            "user_profile": {
                "full_name": "Zoë Sample Person",
                "email": "zoe@example.com",
                "links": [{"label": "GitHub", "url": "github.com/example"}],
            },
            "summary": "Developer focused on accessible web applications.",
            "skills": ["JavaScript", "TypeScript", "React"],
            "experience": [{"role": "Software Developer", "company": "Example Studio", "duration": "2024–2026", "description": "Built a searchable application used by the team."}],
            "education": [{"degree": "BSc Computer Science", "institution": "Example University", "graduation_year": "2024"}],
            "projects": [],
            "certificates": [{"name": "Web Accessibility", "issuer": "Example Institute", "date": "2025"}],
            "awards": [{"name": "Design Award", "issuer": "Example Guild", "date": "2025", "description": "Recognized for accessible design."}],
            "languages": [{"name": "English", "proficiency": "Fluent"}],
            "ai_config": {"provider": "openai", "model": "", "cloud_authorized": False},
        })

    @staticmethod
    def request(method="GET", cookies=None, headers=None):
        raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
        if cookies:
            raw_headers.append((b"cookie", "; ".join(f"{key}={value}" for key, value in cookies.items()).encode()))
        return Request({"type": "http", "method": method, "path": "/api/test", "raw_path": b"/api/test", "query_string": b"", "headers": raw_headers, "client": ("127.0.0.1", 1234), "server": ("test", 80), "scheme": "http", "root_path": ""})

    def test_session_authorization_and_csrf(self):
        response = Response()
        set_session(response, self.user_a["id"])
        cookie = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        user = get_current_user(self.request(cookies={settings.session_cookie_name: cookie}))
        self.assertEqual(user["id"], self.user_a["id"])
        with self.assertRaises(HTTPException) as unauthorized:
            get_current_user(self.request())
        self.assertEqual(unauthorized.exception.status_code, 401)

        self.user_a["session_version"] += 1
        file_store.save_record("users", self.user_a)
        with self.assertRaises(HTTPException) as expired:
            get_current_user(self.request(cookies={settings.session_cookie_name: cookie}))
        self.assertEqual(expired.exception.status_code, 401)

    def test_register_login_logout(self):
        csrf = "synthetic-csrf-token-for-test"
        request = self.request("POST", cookies={"nhyapu_csrf": csrf}, headers={"x-csrf-token": csrf})
        credentials = auth.Credentials(email="new-user@example.com", password="Synthetic-Test-Password-2026!", display_name="New Test User")
        registered_response = Response()
        registered = auth.register(credentials, request, registered_response)
        self.assertEqual(registered["user"]["email"], "new-user@example.com")
        cookie_values = {}
        for raw_name, raw_value in registered_response.raw_headers:
            if raw_name.lower() == b"set-cookie":
                pair = raw_value.decode().split(";", 1)[0]
                name, value = pair.split("=", 1)
                cookie_values[name] = value
        self.assertIn(settings.session_cookie_name, cookie_values)

        login_response = Response()
        logged_in = auth.login(credentials, request, login_response)
        self.assertEqual(logged_in["user"]["id"], registered["user"]["id"])
        for raw_name, raw_value in login_response.raw_headers:
            if raw_name.lower() == b"set-cookie":
                pair = raw_value.decode().split(";", 1)[0]
                name, value = pair.split("=", 1)
                cookie_values[name] = value

        logout_request = self.request("POST", cookies={**cookie_values, "nhyapu_csrf": csrf}, headers={"x-csrf-token": csrf})
        logout_response = Response()
        self.assertEqual(auth.logout(logout_request, logout_response)["ok"], True)
        with self.assertRaises(HTTPException):
            get_current_user(self.request(cookies=cookie_values))

    def test_password_recovery_and_account_deletion(self):
        csrf = "synthetic-csrf-token-for-test"
        request = self.request("POST", cookies={"nhyapu_csrf": csrf}, headers={"x-csrf-token": csrf})
        reset_token = secrets.token_urlsafe(32)
        self.user_a["password_hash"] = auth._password_hash("Old-Synthetic-Password-2026!")
        self.user_a["password_reset_hash"] = auth._token_digest(reset_token)
        self.user_a["password_reset_expires_at"] = 4_000_000_000
        file_store.save_record("users", self.user_a)
        reset = auth.PasswordReset(token=reset_token, password="New-Synthetic-Password-2026!")
        result = auth.reset_password(reset, request)
        self.assertTrue(result["ok"])
        reloaded = file_store.get_record("users", "id", self.user_a["id"])
        self.assertTrue(auth._password_matches("New-Synthetic-Password-2026!", reloaded["password_hash"]))

        generated_account = Path(settings.generated_dir) / self.user_a["id"]
        generated_account.mkdir(parents=True)
        (generated_account / "private.pdf").write_bytes(b"synthetic")
        delete_response = Response()
        deleted = auth.delete_account(request, delete_response, reloaded)
        self.assertTrue(deleted["ok"])
        self.assertIsNone(file_store.get_record("users", "id", self.user_a["id"]))
        self.assertFalse(generated_account.exists())

    def test_brevo_smtp_verification_uses_starttls(self):
        previous = (settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password, settings.smtp_from_email, settings.require_email_verification)
        settings.smtp_host = "smtp-relay.brevo.com"
        settings.smtp_port = 587
        settings.smtp_username = "synthetic-smtp-login@example.test"
        settings.smtp_password = "synthetic-brevo-smtp-key"
        settings.smtp_from_email = "verified-sender@example.test"
        settings.require_email_verification = True
        try:
            csrf = "synthetic-csrf-token-for-test"
            request = self.request("POST", cookies={"nhyapu_csrf": csrf}, headers={"x-csrf-token": csrf})
            credentials = auth.Credentials(email="verify-user@example.com", password="Synthetic-Test-Password-2026!")
            response = Response()
            with patch("app.routers.auth._send_email", return_value=True) as send_email:
                result = auth.register(credentials, request, response)
            self.assertTrue(result["verification_required"])
            self.assertIn("smtp-relay.brevo.com", settings.smtp_host)
            self.assertIn("/api/auth/verify?token=", send_email.call_args.args[2])

            smtp_client = unittest.mock.MagicMock()
            smtp_context = unittest.mock.MagicMock()
            smtp_context.__enter__.return_value = smtp_client
            with patch("app.routers.auth.smtplib.SMTP", return_value=smtp_context) as smtp:
                self.assertTrue(auth._send_email("person@example.test", "Verify", "Synthetic verification message"))
            smtp.assert_called_once_with("smtp-relay.brevo.com", 587, timeout=15)
            smtp_client.starttls.assert_called_once()
            smtp_client.login.assert_called_once_with("synthetic-smtp-login@example.test", "synthetic-brevo-smtp-key")
        finally:
            (settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password, settings.smtp_from_email, settings.require_email_verification) = previous

    def test_create_read_update_rename_duplicate_delete_and_owner_checks(self):
        created = resumes.create_resume(self.payload(), current_user=self.user_a)
        resume_id = created.id
        self.assertEqual(created.page_size, "a4")
        self.assertEqual(resumes.list_resumes(current_user=self.user_a)[0].file_name, "Test Resume")
        self.assertEqual(resumes.list_resumes(current_user=self.user_b), [])
        self.assertEqual(resumes.get_resume(resume_id, current_user=self.user_a).id, resume_id)

        with self.assertRaises(HTTPException) as denied:
            resumes.get_resume(resume_id, current_user=self.user_b)
        self.assertEqual(denied.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            resumes.delete_resume(resume_id, current_user=self.user_b)
        with self.assertRaises(HTTPException):
            resumes.get_resume_pdf(resume_id, current_user=self.user_b)

        if created.pdf_path:
            pdf_response = resumes.get_resume_pdf(resume_id, current_user=self.user_a)
            pdf_bytes = Path(pdf_response.path).read_bytes()
            from pypdf import PdfReader
            pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
            self.assertIn("Zoë Sample Person", pdf_text)
            self.assertIn("React", pdf_text)
            self.assertIn("Fluent", pdf_text)
        else:
            self.assertTrue(created.docx_path and Path(created.docx_path).is_file())

        update = self.payload("Updated Resume")
        update.page_size = "letter"
        update.expected_updated_at = created.updated_at.isoformat()
        updated = resumes.update_resume(resume_id, update, current_user=self.user_a)
        self.assertEqual(updated.page_size, "letter")
        renamed = resumes.rename_resume(resume_id, resumes.ResumeTitleUpdate(title="Renamed Resume"), current_user=self.user_a)
        self.assertEqual(renamed.file_name, "Renamed Resume")
        duplicate = resumes.duplicate_resume(resume_id, current_user=self.user_a)
        self.assertNotEqual(duplicate.id, resume_id)
        self.assertEqual(duplicate.file_name, "Renamed Resume copy")
        result = resumes.delete_resume(resume_id, current_user=self.user_a)
        self.assertEqual(result.status_code, 204)
        with self.assertRaises(HTTPException):
            resumes.get_resume(resume_id, current_user=self.user_a)

    def test_model_validation_and_manual_creation_without_ai(self):
        invalid = self.payload().model_dump()
        invalid["template_name"] = "creative"
        with self.assertRaises(Exception):
            resumes._validate_layout_selection(CreateResumeRequest.model_validate(invalid), self.user_a["id"])
        record = resumes.create_resume(self.payload(), current_user=self.user_a)
        self.assertTrue(record.docx_path and Path(record.docx_path).is_file())
        if not record.pdf_path:
            self.skipTest("The container's LibreOffice PDF process cannot write its runtime profile.")
        self.assertTrue(Path(record.pdf_path).is_file())

    def test_custom_ai_key_is_masked_and_used_without_server_key(self):
        custom = "synthetic-user-api-key-DO-NOT-LOG"
        config = AIConfig(provider="openai", model="synthetic-model", cloud_authorized=True, api_key=custom)
        self.assertNotIn(custom, repr(config))
        provider = unittest.mock.MagicMock(name="OpenAIProvider")
        with patch.dict(llm_providers._PROVIDER_MAP, {"openai": provider}):
            llm_providers.get_llm_provider(config)
        self.assertEqual(provider.call_args.kwargs["api_key"], custom)
        self.assertEqual(provider.call_args.kwargs["model"], "synthetic-model")
        self.assertEqual(resumes._safe_error(RuntimeError(f"bad key {custom}"), custom), "bad key [redacted]")

    def test_groq_custom_key_uses_groq_compatible_endpoint(self):
        provider = unittest.mock.MagicMock(name="GroqProvider")
        with patch.dict(llm_providers._PROVIDER_MAP, {"groq": provider}):
            llm_providers.get_llm_provider(AIConfig(provider="groq", model="openai/gpt-oss-20b", cloud_authorized=True, api_key="synthetic-groq-key"))
        self.assertEqual(provider.call_args.kwargs["api_key"], "synthetic-groq-key")
        self.assertEqual(provider.call_args.kwargs["base_url"], "https://api.groq.com/openai/v1")

    def test_api_key_is_not_saved_with_resume(self):
        payload = self.payload()
        payload.ai_config = AIConfig(provider="openai", cloud_authorized=True, api_key="synthetic-never-persist-this")
        record = resumes.create_resume(payload, current_user=self.user_a)
        persisted = file_store.get_record("resumes", "id", record.id)
        self.assertNotIn("ai_config", persisted.get("source_data", {}))
        self.assertNotIn("synthetic-never-persist-this", str(persisted))

    def test_all_five_templates_render_from_shared_resume_data(self):
        layouts = {
            "ats": "ats-standard",
            "modern": "modern-minimalist",
            "student": "student-graduate",
            "developer": "technical-developer",
            "research": "ai-ml-research",
        }
        for template_name, layout_id in layouts.items():
            with self.subTest(template=template_name):
                payload = self.payload(f"{template_name.title()} Resume")
                payload.template_name = template_name
                payload.layout_id = layout_id
                record = resumes.create_resume(payload, current_user=self.user_a)
                self.assertEqual(record.template_name, template_name)
                self.assertEqual(record.structured_data["header"]["full_name"], "Zoë Sample Person")
                self.assertTrue(record.docx_path and Path(record.docx_path).is_file())


if __name__ == "__main__":
    unittest.main()
