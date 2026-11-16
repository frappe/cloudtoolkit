### SSH

Run scripts on, and copy files to, remote hosts over the system `ssh` and `rsync`, and stream their output into a document field while they run.

### Running a script

`SSHClient` pipes a script to `bash -s` on one host and returns an `SSHResult` with `output` and `exit_code`.

```python
from cloudtoolkit.ssh.client import SSHClient, SSHError, SSHTimeoutError

client = SSHClient(machine.address, user="root", port=22, private_key=machine.get_password("ssh_private_key"))
result = client.run("df -h /", environment={"LANG": "C"}, timeout_seconds=60)
print(result.output)
```

- A non-zero exit raises `SSHError` with the last 3,000 characters of output. Pass `check=False` to get the result back instead.
- A run past `timeout_seconds` (600 by default) is killed and raises `SSHTimeoutError`.
- `environment` is exported ahead of the script. Names must be identifiers, and values are shell-quoted.
- `on_output` is called with each piece of output as it arrives.
- Without `private_key`, ssh uses the bench user's own keys. With it, the key is written to an owner-only temporary file and only that key is offered.
- New host keys are accepted and never written to `known_hosts`. Batch mode is on, so ssh never prompts.

### Scripts shipped in an app

`read_script` reads a script from an app folder and exports its environment ahead of it:

```python
from cloudtoolkit.ssh.client import read_script

client.run(read_script("cargo", "caddy", "install.sh", environment={"CADDYFILE": caddyfile}))
```

### Copying files

`rsync` copies a folder's contents into a destination, or a file to that path. Existing remote folders keep their owner and permissions, and new files keep only their executable bit.

```python
from pathlib import Path

client.rsync(Path(frappe.get_app_path("my_app", "config", "caddy")), "/etc/caddy")
```

### Hosts behind a proxy

A guest reachable only through its host uses the host's ssh as its `ProxyCommand`. The proxy host must use the default identity.

```python
host = SSHClient("fdab:1::7")
guest = SSHClient("vm-00001", proxy_command=host.get_proxy_command("nc 172.16.0.2 22"))
```

### Waiting for a new server

`wait_for_server` polls until SSH accepts one of the given users and returns that user:

```python
from cloudtoolkit.ssh.client import wait_for_server

user = wait_for_server(address, users=("ubuntu", "root"), timeout_seconds=300, poll_interval_seconds=5)
```

`client.is_reachable` checks once, and `create_keypair(comment)` returns a fresh ed25519 `(public, private)` keypair.

### Live output

`OutputLog` streams a command's output into a document field. While the command runs, the output is kept in the cache and published on the `ssh_output` realtime event, so the run never locks the row. Once it ends, the output is stored in the field.

```python
from cloudtoolkit.ssh.output_log import OutputLog

with OutputLog(machine, "setup_log") as log:
	client.run(script, on_output=log.write)
```

- Pass `append=True` to add to the field instead of replacing it.
- `live_output(document, fieldname)` returns the output so far: the cache while it runs, the field once it ends.
- A form reads it with the whitelisted `cloudtoolkit.ssh.output_log.get_live_output(doctype, name, fieldname)`, which checks read permission on the document and the field, and listens on `ssh_output` for updates:

```javascript
frappe.realtime.on("ssh_output", ({ name, fieldname, value }) => {
	if (name !== frm.doc.name) return;
	frm.doc[fieldname] = value;
	frm.refresh_field(fieldname);
});
```

### Tests

Patch `cloudtoolkit.ssh.client.SSHClient.run` or `.rsync` to keep tests off the network, or `cloudtoolkit.ssh.client.stream` to check the exact command line.
