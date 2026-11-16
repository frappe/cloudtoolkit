from __future__ import annotations

import codecs
import os
import selectors
import shlex
import stat
import subprocess
import tempfile
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep

import frappe

DEFAULT_TIMEOUT_SECONDS = 600
ERROR_TAIL_CHARACTERS = 3_000
OPTIONS = (
	"-o",
	"StrictHostKeyChecking=accept-new",
	"-o",
	"UserKnownHostsFile=/dev/null",
	"-o",
	"GlobalKnownHostsFile=/dev/null",
	"-o",
	"LogLevel=ERROR",
	"-o",
	"BatchMode=yes",
	"-o",
	"ConnectTimeout=15",
	# A machine terminated mid-command sends no reset, so without these ssh would wait forever.
	"-o",
	"ServerAliveInterval=15",
	"-o",
	"ServerAliveCountMax=3",
)


class SSHError(RuntimeError):
	"""A command run over SSH failed. One argument, so the pipeline engine can pickle it."""


class SSHTimeoutError(SSHError):
	"""A command run over SSH outlived its timeout and was killed."""


@dataclass(frozen=True, slots=True)
class SSHResult:
	"""What one SSH command printed, and how it exited."""

	output: str
	exit_code: int

	@property
	def is_success(self) -> bool:
		return self.exit_code == 0


class SSHClient:
	"""Run scripts on, and copy files to, one SSH host."""

	def __init__(
		self,
		host: str,
		*,
		user: str = "root",
		port: int = 22,
		private_key: str | None = None,
		proxy_command: str | None = None,
	) -> None:
		if not host:
			raise ValueError("SSH host is required")
		if not user:
			raise ValueError("SSH user is required")
		if not 1 <= port <= 65_535:
			raise ValueError(f"Invalid SSH port: {port}")
		if private_key is not None and not private_key.strip():
			raise ValueError(f"The SSH private key for {host} is empty")

		self.host = host
		self.user = user
		self.port = port
		self.private_key = private_key
		self.proxy_command = proxy_command

	def run(
		self,
		script: str,
		*,
		environment: Mapping[str, object] | None = None,
		timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
		on_output: Callable[[str], None] | None = None,
		check: bool = True,
	) -> SSHResult:
		"""Pipe a script to `bash -s`. With `check`, a non-zero exit raises `SSHError`."""
		with self.identity() as options:
			command = ["ssh", *options, f"{self.user}@{self.host}", "bash -s"]
			result = stream(command, with_environment(script, environment), timeout_seconds, on_output)

		return self.checked(result) if check else result

	def rsync(
		self,
		source: Path,
		destination: str,
		*,
		timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
		on_output: Callable[[str], None] | None = None,
	) -> SSHResult:
		"""Copy a folder's contents into `destination`, or a file to that path. Existing folders keep
		their owner and permissions, and new files keep only their executable bit, so `/etc` is never loosened.
		"""
		with self.identity() as options:
			# No --owner or --group: they reset every folder on the path, so a package's own folder
			# such as /etc/redis (redis:redis 2770) would become root's and lock the package out.
			command = [
				"rsync",
				"--recursive",
				"--links",
				"--times",
				"--omit-dir-times",
				"--executability",
				"--mkpath",
				"--rsh",
				shlex.join(["ssh", *options]),
				f"{source}/" if source.is_dir() else str(source),
				f"{self.user}@[{self.host}]:{destination}",
			]
			result = stream(command, "", timeout_seconds, on_output)

		return self.checked(result)

	@property
	def is_reachable(self) -> bool:
		try:
			return self.run("true", timeout_seconds=10, check=False).is_success
		except (OSError, SSHError):
			return False

	def get_proxy_command(self, command: str) -> str:
		"""An ssh command line that runs `command` on this host, for use as another host's ProxyCommand."""
		if self.private_key:
			raise ValueError("A proxy host must use the default SSH identity")

		return shlex.join(["ssh", *self.options, f"{self.user}@{self.host}", command])

	@property
	def options(self) -> list[str]:
		proxy = ["-o", f"ProxyCommand={self.proxy_command}"] if self.proxy_command else []
		return ["-p", str(self.port), *OPTIONS, *proxy]

	@contextmanager
	def identity(self) -> Generator[list[str]]:
		"""The ssh options, with the private key on disk for as long as ssh needs it."""
		with private_key_file(self.private_key) if self.private_key else nullcontext() as path:
			yield [*self.options, "-o", "IdentitiesOnly=yes", "-i", path] if path else self.options

	def checked(self, result: SSHResult) -> SSHResult:
		if not result.is_success:
			raise SSHError(
				f"{self.host} exited {result.exit_code}:\n...{result.output[-ERROR_TAIL_CHARACTERS:]}"
			)

		return result


def stream(
	command: list[str], stdin: str, timeout_seconds: int, on_output: Callable[[str], None] | None
) -> SSHResult:
	"""Run a command and collect what it prints, passing each piece to `on_output` as it arrives."""
	if timeout_seconds <= 0:
		raise ValueError(f"Invalid SSH timeout: {timeout_seconds}")

	process = subprocess.Popen(
		command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
	)
	process.stdin.write(stdin.encode())
	process.stdin.close()

	decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
	output: list[str] = []
	deadline = monotonic() + timeout_seconds
	with selectors.DefaultSelector() as selector:
		selector.register(process.stdout, selectors.EVENT_READ)
		while selector.get_map():
			remaining = deadline - monotonic()
			if remaining <= 0:
				process.kill()
				process.wait()
				tail = "".join(output)[-ERROR_TAIL_CHARACTERS:]
				raise SSHTimeoutError(f"{command[0]} timed out after {timeout_seconds}s:\n...{tail}")
			for key, _ in selector.select(remaining):
				chunk = os.read(key.fd, 4_096)
				text = decoder.decode(chunk, final=not chunk)
				if not chunk:
					selector.unregister(key.fileobj)
				if text:
					output.append(text)
					if on_output:
						on_output(text)

	return SSHResult(output="".join(output), exit_code=process.wait())


def wait_for_server(
	host: str,
	*,
	users: tuple[str, ...] = ("root",),
	timeout_seconds: int,
	poll_interval_seconds: int,
	private_key: str | None = None,
	proxy_command: str | None = None,
) -> str:
	"""The first of `users` that SSH accepts on the host, once it does."""
	if not users:
		raise ValueError("At least one SSH user is required")
	if poll_interval_seconds <= 0:
		raise ValueError(f"Invalid SSH poll interval: {poll_interval_seconds}")

	clients = [
		SSHClient(host, user=user, private_key=private_key, proxy_command=proxy_command) for user in users
	]
	deadline = monotonic() + timeout_seconds
	while monotonic() < deadline:
		for client in clients:
			if client.is_reachable:
				return client.user
		sleep(poll_interval_seconds)

	raise SSHTimeoutError(f"SSH on {host} did not become ready within {timeout_seconds} seconds")


def create_keypair(comment: str) -> tuple[str, str]:
	"""A fresh ed25519 keypair, as (public, private)."""
	with tempfile.TemporaryDirectory() as directory:
		path = Path(directory) / "key"
		subprocess.run(
			["ssh-keygen", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path)],
			check=True,
			capture_output=True,
		)

		return path.with_suffix(".pub").read_text().strip(), path.read_text()


@contextmanager
def private_key_file(key: str) -> Generator[str]:
	"""The key in a file only its owner can read, deleted on exit."""
	with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
		key_file.write(key if key.endswith("\n") else f"{key}\n")
		path = key_file.name
	os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
	try:
		yield path
	finally:
		os.unlink(path)


def with_environment(script: str, environment: Mapping[str, object] | None = None) -> str:
	"""The script with each variable exported ahead of it."""
	exports = []
	for name, value in (environment or {}).items():
		if not name.isidentifier():
			raise ValueError(f"Invalid environment variable name: {name}")
		exports.append(f"export {name}={shlex.quote(str(value))}")

	return "\n".join((*exports, script))


def read_script(app: str, *path: str, environment: Mapping[str, object] | None = None) -> str:
	"""A script shipped in an app, such as `read_script("cargo", "caddy", "install.sh")`, with its
	environment exported ahead of it."""
	return with_environment(Path(frappe.get_app_path(app, *path)).read_text(), environment)
