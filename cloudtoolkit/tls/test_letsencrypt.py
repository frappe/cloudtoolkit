from __future__ import annotations

from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import ec
from frappe.tests import UnitTestCase

from cloudtoolkit.tls.acme import DnsChallenge, Order
from cloudtoolkit.tls.certificate import create_private_key, serialize_private_key
from cloudtoolkit.tls.letsencrypt import (
	DIRECTORY_URLS,
	IssuedCertificate,
	LetsEncrypt,
	LetsEncryptError,
	create_account_key,
)
from cloudtoolkit.tls.test_certificate import self_signed_certificate

MODULE = "cloudtoolkit.tls.letsencrypt"
NAMES = ["s3-svc.example.com", "s3-admin-svc.example.com"]


def _challenge(index: int, record_name: str) -> DnsChallenge:
	return DnsChallenge(
		challenge_url=f"https://acme.test/challenge/{index}",
		record_name=record_name,
		record_value=f"value-{index}",
	)


class TestLetsEncryptAccount(UnitTestCase):
	def test_a_new_account_key_loads_as_an_ec_key(self) -> None:
		issuer = LetsEncrypt(create_account_key(), "owner@example.com", MagicMock())

		self.assertIsInstance(issuer.account_key, ec.EllipticCurvePrivateKey)

	def test_staging_uses_the_staging_directory(self) -> None:
		issuer = LetsEncrypt(create_account_key(), "owner@example.com", MagicMock(), is_staging=True)

		self.assertEqual(issuer.directory_url, DIRECTORY_URLS["Staging"])

	def test_a_key_that_is_not_an_ec_key_is_refused(self) -> None:
		issuer = LetsEncrypt(serialize_private_key(create_private_key()), "owner@example.com", MagicMock())

		with self.assertRaises(LetsEncryptError):
			issuer.account_key

	def test_text_that_is_not_a_key_is_refused(self) -> None:
		issuer = LetsEncrypt("not a key", "owner@example.com", MagicMock())

		with self.assertRaises(LetsEncryptError):
			issuer.account_key


class TestLetsEncryptIssuance(UnitTestCase):
	def setUp(self) -> None:
		self.records = MagicMock()
		self.issuer = LetsEncrypt(create_account_key(), "owner@example.com", self.records)
		self.issuer.DNS_PROPAGATION_DELAY = 0

		self.client = MagicMock()
		self.client.create_order.return_value = Order(
			url="https://acme.test/order/1",
			authorization_urls=["https://acme.test/authz/1", "https://acme.test/authz/2"],
			finalize_url="https://acme.test/order/1/finalize",
		)
		self.client.get_dns_challenge.side_effect = [
			_challenge(1, "_acme-challenge.s3-svc.example.com"),
			_challenge(2, "_acme-challenge.s3-admin-svc.example.com"),
		]
		self.client.finalize_order.return_value = "https://acme.test/cert/1"
		patched = patch(f"{MODULE}.AcmeClient", return_value=self.client)
		self.addCleanup(patched.stop)
		self.acme_client = patched.start()

	def _issue(self) -> IssuedCertificate:
		self.client.download_certificate.return_value = self_signed_certificate(create_private_key(), NAMES)
		return self.issuer.issue_certificate(NAMES)

	def test_issuance_proves_control_through_dns_and_returns_the_certificate(self) -> None:
		issued = self._issue()

		directory_url, account_key = self.acme_client.call_args.args
		self.assertEqual(directory_url, DIRECTORY_URLS["Production"])
		self.assertIsInstance(account_key, ec.EllipticCurvePrivateKey)
		self.client.register_account.assert_called_once_with("owner@example.com")
		self.client.create_order.assert_called_once_with(NAMES)
		self.records.set_txt_record.assert_any_call("_acme-challenge.s3-svc.example.com", ["value-1"])
		self.records.set_txt_record.assert_any_call("_acme-challenge.s3-admin-svc.example.com", ["value-2"])
		self.assertEqual(self.client.submit_challenge.call_count, 2)
		self.assertEqual(self.client.wait_for_authorization.call_count, 2)
		self.assertIn("BEGIN CERTIFICATE", issued.certificate_pem)
		self.assertIn("BEGIN PRIVATE KEY", issued.private_key_pem)
		self.assertIsNotNone(issued.expires_on)

	def test_values_under_one_record_name_are_published_together(self) -> None:
		self.client.get_dns_challenge.side_effect = [
			_challenge(1, "_acme-challenge.example.com"),
			_challenge(2, "_acme-challenge.example.com"),
		]

		self._issue()

		self.records.set_txt_record.assert_called_once_with(
			"_acme-challenge.example.com", ["value-1", "value-2"]
		)
		self.records.remove_txt_record.assert_called_once_with("_acme-challenge.example.com")

	def test_the_challenge_records_are_removed_after_a_successful_issuance(self) -> None:
		self._issue()

		self.assertEqual(self.records.remove_txt_record.call_count, 2)

	def test_the_challenge_records_are_removed_after_a_failed_order(self) -> None:
		self.client.finalize_order.side_effect = RuntimeError("order failed")

		with self.assertRaises(RuntimeError):
			self.issuer.issue_certificate(NAMES)

		self.assertEqual(self.records.remove_txt_record.call_count, 2)

	def test_a_failed_cleanup_does_not_hide_the_issuance_failure(self) -> None:
		self.client.finalize_order.side_effect = RuntimeError("order failed")
		self.records.remove_txt_record.side_effect = OSError("dns down")

		with patch(f"{MODULE}.frappe.log_error") as log_error, self.assertRaisesRegex(RuntimeError, "order"):
			self.issuer.issue_certificate(NAMES)

		self.assertEqual(log_error.call_count, 2)

	def test_issuance_without_an_email_is_refused(self) -> None:
		self.issuer.email = ""

		with self.assertRaises(LetsEncryptError):
			self.issuer.issue_certificate(NAMES)

		self.client.create_order.assert_not_called()

	def test_issuance_without_names_is_refused(self) -> None:
		with self.assertRaises(LetsEncryptError):
			self.issuer.issue_certificate([])

		self.client.create_order.assert_not_called()
