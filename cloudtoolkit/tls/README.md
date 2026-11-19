### TLS

Issue Let's Encrypt certificates with the ACME dns-01 challenge, so one certificate can serve any number of machines behind one name.

### Issuing a certificate

`LetsEncrypt` takes an ACME account key, a contact email, and an object that publishes the challenge TXT records. `issue_certificate` returns an `IssuedCertificate` with `certificate_pem`, `private_key_pem`, and `expires_on` (UTC).

```python
from cloudtoolkit.tls.letsencrypt import LetsEncrypt, create_account_key


class ChallengeRecords:
	def set_txt_record(self, name: str, values: list[str]) -> None:
		dns.upsert_record("TXT", name, [f'"{value}"' for value in values], ttl=60)

	def remove_txt_record(self, name: str) -> None:
		dns.remove_record("TXT", name)


account_key = settings.get_password("acme_account_key") or create_account_key()
issuer = LetsEncrypt(account_key, "ops@example.com", ChallengeRecords(), is_staging=False)
issued = issuer.issue_certificate(["s3-svc.example.com", "s3-admin-svc.example.com"])
```

- The caller stores the account key, for example in a Password field. Reuse it: Let's Encrypt rate-limits new accounts.
- TXT values arrive unquoted. Quote them if the DNS provider needs it, as Route 53 does.
- Every name in the order gets its own challenge. `*.x` and `x` share `_acme-challenge.x`, so that record gets both values in one call.
- The records are published, then the issuer waits `DNS_PROPAGATION_DELAY` (30) seconds before Let's Encrypt checks them.
- The records are removed after issuance, even when it fails. A failed removal is logged and never hides the issuance error.
- Pass `is_staging=True` while testing: staging certificates are not trusted, but its rate limits are much higher.

### Lower-level pieces

- `cloudtoolkit.tls.acme.AcmeClient` speaks ACME v2 for one EC account key: account, order, dns-01 challenge, finalize, download.
- `cloudtoolkit.tls.certificate` creates RSA keys and certificate requests, reads a certificate's expiry and names with `read_certificate`, and checks a key matches a certificate with `verify_key_pair`.

### Tests

Set `DNS_PROPAGATION_DELAY = 0` on the issuer and patch `cloudtoolkit.tls.letsencrypt.AcmeClient` to keep tests off the network.
