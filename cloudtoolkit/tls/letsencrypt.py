from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import frappe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from cloudtoolkit.tls.acme import AcmeClient, DnsChallenge
from cloudtoolkit.tls.certificate import (
	create_certificate_request,
	create_private_key,
	read_certificate,
	serialize_private_key,
)

DIRECTORY_URLS = {
	"Production": "https://acme-v02.api.letsencrypt.org/directory",
	"Staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
}


class LetsEncryptError(Exception):
	"""Raised when a certificate cannot be issued from Let's Encrypt."""


class ChallengeRecords(Protocol):
	"""Publishes the dns-01 TXT records. Values arrive unquoted; quote them if the provider needs it."""

	def set_txt_record(self, name: str, values: list[str]) -> None: ...

	def remove_txt_record(self, name: str) -> None: ...


@dataclass(frozen=True)
class IssuedCertificate:
	"""One issued certificate chain, its private key, and its UTC expiry."""

	certificate_pem: str
	private_key_pem: str
	expires_on: datetime


def create_account_key() -> str:
	"""Return a new ACME account key as unencrypted PKCS#8 PEM."""
	return (
		ec.generate_private_key(ec.SECP256R1())
		.private_bytes(
			encoding=serialization.Encoding.PEM,
			format=serialization.PrivateFormat.PKCS8,
			encryption_algorithm=serialization.NoEncryption(),
		)
		.decode()
	)


class LetsEncrypt:
	"""Issue certificates with the ACME dns-01 challenge for one account."""

	DNS_PROPAGATION_DELAY = 30

	def __init__(
		self,
		account_key_pem: str,
		email: str,
		challenge_records: ChallengeRecords,
		is_staging: bool = False,
	) -> None:
		self.account_key_pem = account_key_pem
		self.email = email
		self.challenge_records = challenge_records
		self.is_staging = is_staging

	@property
	def environment(self) -> str:
		return "Staging" if self.is_staging else "Production"

	@property
	def directory_url(self) -> str:
		return DIRECTORY_URLS[self.environment]

	@property
	def account_key(self) -> ec.EllipticCurvePrivateKey:
		try:
			private_key = serialization.load_pem_private_key(self.account_key_pem.encode(), password=None)
		except (ValueError, TypeError) as error:
			raise LetsEncryptError("The ACME account key is not valid PEM.") from error
		if not isinstance(private_key, ec.EllipticCurvePrivateKey):
			raise LetsEncryptError("The ACME account key is not an EC key.")
		return private_key

	def issue_certificate(self, dns_names: list[str]) -> IssuedCertificate:
		"""Issue one certificate for the DNS names. The challenge records are removed even on failure."""
		if not self.email:
			raise LetsEncryptError("Set the Let's Encrypt email before issuing.")
		if not dns_names:
			raise LetsEncryptError("A certificate needs at least one DNS name.")

		client = AcmeClient(self.directory_url, self.account_key)
		client.register_account(self.email)

		order = client.create_order(dns_names)
		challenges = [client.get_dns_challenge(url) for url in order.authorization_urls]
		try:
			self.prove_control(client, order.authorization_urls, challenges)
			private_key = create_private_key()
			request = create_certificate_request(private_key, dns_names)
			certificate_url = client.finalize_order(order, request)
			certificate_pem = client.download_certificate(certificate_url)
		finally:
			self.remove_challenge_records(challenges)

		return IssuedCertificate(
			certificate_pem=certificate_pem,
			private_key_pem=serialize_private_key(private_key),
			expires_on=read_certificate(certificate_pem).expires_on,
		)

	def prove_control(
		self, client: AcmeClient, authorization_urls: list[str], challenges: list[DnsChallenge]
	) -> None:
		"""Publish every TXT value, then let the server check each authorization."""
		for record_name, values in group_values(challenges).items():
			self.challenge_records.set_txt_record(record_name, values)

		time.sleep(self.DNS_PROPAGATION_DELAY)

		for challenge in challenges:
			client.submit_challenge(challenge.challenge_url)
		for authorization_url in authorization_urls:
			client.wait_for_authorization(authorization_url)

	def remove_challenge_records(self, challenges: list[DnsChallenge]) -> None:
		"""Remove the challenge records. A failure here must not hide an issuance failure."""
		for record_name in group_values(challenges):
			try:
				self.challenge_records.remove_txt_record(record_name)
			except Exception:
				frappe.log_error(title=f"Unable to remove ACME record {record_name}")


def group_values(challenges: list[DnsChallenge]) -> dict[str, list[str]]:
	"""Group values by record name. `*.x` and `x` share one name, so it holds both values."""
	grouped: dict[str, list[str]] = defaultdict(list)
	for challenge in challenges:
		grouped[challenge.record_name].append(challenge.record_value)
	return dict(grouped)
