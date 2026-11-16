import os
import stat
from pathlib import Path
from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from cloudtoolkit.ssh.client import (
	SSHClient,
	SSHError,
	SSHResult,
	SSHTimeoutError,
	create_keypair,
	private_key_file,
	stream,
	wait_for_server,
	with_environment,
)

MODULE = "cloudtoolkit.ssh.client"


class TestSSHClient(UnitTestCase):
	def run_with(self, client: SSHClient, result: SSHResult, **kwargs) -> tuple[Mock, SSHResult]:
		with patch(f"{MODULE}.stream", return_value=result) as fake:
			return fake, client.run("echo $MESSAGE", **kwargs)

	def test_run_pipes_the_script_with_its_environment(self):
		fake, result = self.run_with(
			SSHClient("203.0.113.1", user="ubuntu", port=2222),
			SSHResult("done", 0),
			environment={"MESSAGE": "hello world"},
		)

		command, stdin, *_ = fake.call_args.args
		self.assertEqual(result.output, "done")
		self.assertEqual(command[:3], ["ssh", "-p", "2222"])
		self.assertEqual(command[-2:], ["ubuntu@203.0.113.1", "bash -s"])
		self.assertNotIn("-i", command)
		self.assertEqual(stdin, "export MESSAGE='hello world'\necho $MESSAGE")

	def test_a_private_key_is_used_alone_and_removed_after(self):
		paths = []

		def fake_stream(command, *args):
			path = command[command.index("-i") + 1]
			paths.append(path)
			self.assertEqual(Path(path).read_text(), "KEY\n")
			self.assertIn("IdentitiesOnly=yes", command)
			return SSHResult("", 0)

		with patch(f"{MODULE}.stream", side_effect=fake_stream):
			SSHClient("203.0.113.1", private_key="KEY").run("true")

		self.assertFalse(Path(paths[0]).exists())

	def test_a_failed_command_raises_with_its_output(self):
		with self.assertRaisesRegex(SSHError, "203.0.113.1 exited 3:\n...no space left"):
			self.run_with(SSHClient("203.0.113.1"), SSHResult("no space left", 3))

	def test_an_unchecked_failure_returns_the_result(self):
		_fake, result = self.run_with(SSHClient("203.0.113.1"), SSHResult("", 3), check=False)
		self.assertFalse(result.is_success)

	def test_an_empty_private_key_is_refused(self):
		with self.assertRaises(ValueError):
			SSHClient("203.0.113.1", private_key="  ")

	def test_rsync_copies_as_the_user_over_the_same_options(self):
		with patch(f"{MODULE}.stream", return_value=SSHResult("", 0)) as fake:
			SSHClient("fdab:1::7", port=2222).rsync(Path(__file__), "/etc/app.py")

		command = fake.call_args.args[0]
		self.assertEqual(command[0], "rsync")
		self.assertIn("-p 2222", command[command.index("--rsh") + 1])
		self.assertEqual(command[-2:], [__file__, "root@[fdab:1::7]:/etc/app.py"])

	def test_a_guest_connection_runs_through_the_host_proxy_command(self):
		proxy = SSHClient("fdab:1::7").get_proxy_command("nc 172.16.0.2 22")
		with patch(f"{MODULE}.stream", return_value=SSHResult("", 0)) as fake:
			SSHClient("vm-00001", proxy_command=proxy).run("true")

		self.assertIn(f"ProxyCommand={proxy}", fake.call_args.args[0])
		self.assertTrue(proxy.endswith("root@fdab:1::7 'nc 172.16.0.2 22'"))

	def test_a_proxy_host_cannot_use_a_private_key(self):
		with self.assertRaises(ValueError):
			SSHClient("fdab:1::7", private_key="KEY").get_proxy_command("true")


class TestStream(UnitTestCase):
	def test_output_reaches_the_callback_as_it_arrives(self):
		pieces = []
		result = stream(["sh", "-c", "cat; printf 'é'; exit 4"], "in\n", 10, pieces.append)

		self.assertEqual(result, SSHResult("in\né", 4))
		self.assertEqual("".join(pieces), "in\né")

	def test_a_command_past_its_timeout_is_killed(self):
		with self.assertRaisesRegex(SSHTimeoutError, "timed out after 1s:\n...started"):
			stream(["sh", "-c", "echo started; sleep 30"], "", 1, None)


class TestHelpers(UnitTestCase):
	def test_wait_for_server_returns_the_first_user_ssh_accepts(self):
		results = iter((SSHResult("", 255), SSHResult("", 0)))
		with patch(f"{MODULE}.stream", side_effect=lambda *args: next(results)):
			user = wait_for_server(
				"203.0.113.1", users=("ubuntu", "root"), timeout_seconds=5, poll_interval_seconds=1
			)

		self.assertEqual(user, "root")

	def test_wait_for_server_gives_up_at_its_timeout(self):
		with (
			patch(f"{MODULE}.stream", return_value=SSHResult("", 255)),
			patch(f"{MODULE}.sleep"),
			patch(f"{MODULE}.monotonic", side_effect=(0, 0, 10)),
			self.assertRaises(SSHTimeoutError),
		):
			wait_for_server("203.0.113.1", timeout_seconds=5, poll_interval_seconds=1)

	def test_with_environment_quotes_values_and_refuses_bad_names(self):
		self.assertEqual(with_environment("run", {"A": "x y"}), "export A='x y'\nrun")
		self.assertEqual(with_environment("run"), "run")
		with self.assertRaises(ValueError):
			with_environment("run", {"A; rm -rf /": "x"})

	def test_private_key_file_is_owner_only_and_removed(self):
		with private_key_file("KEY") as path:
			self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

		self.assertFalse(Path(path).exists())

	def test_create_keypair(self):
		public, private = create_keypair("machine-1")

		self.assertTrue(public.startswith("ssh-ed25519 ") and public.endswith(" machine-1"))
		self.assertIn("OPENSSH PRIVATE KEY", private)
