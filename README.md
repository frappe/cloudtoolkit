### Cloud Toolkit

Shared building blocks for Frappe Cloud apps: durable pipelines and SSH.

### Installation

You can install this app using the [Pilot](https://github.com/frappe/pilot) CLI:

```bash
pilot -b $BENCH_NAME get-app https://github.com/frappe/cloudtoolkit --branch develop
pilot -b $BENCH_NAME install-app $SITE_NAME cloudtoolkit
```

Add `required_apps = ["cloudtoolkit"]` to the hooks of an app that uses it.

This app was named `pipeline`. Installing it on a site that has `pipeline` takes over the `Pipeline` module, so its tables and rows stay, and drops `pipeline` from the installed apps. Keep the `pipeline` checkout on the bench until every site has this app, and never run `uninstall-app pipeline`: it deletes the Pipeline tables.

### Pipeline

A pipeline runs the `@task` steps of a `@flow` method in background jobs. Each finished step is stored, so a retried or restarted pipeline skips the steps that already ran.

```python
from cloudtoolkit.pipeline.doctype.pipeline.decorators import flow, task
from cloudtoolkit.pipeline.doctype.pipeline.pipeline_builder import PipelineBuilder


class DeployRequest(PipelineBuilder):
	@flow
	def deploy(self):
		server = self.provision()
		self.build(server)

	@task
	def provision(self) -> str:
		if not self.is_ready():
			self.defer_current_task("Server is still booting.")  # runs this step again later
		return "server-1"

	@task
	def build(self, server: str): ...

	def on_pipeline_success(self, pipeline): ...
	def on_pipeline_failure(self, pipeline): ...


DeployRequest("...").deploy.run_as_pipeline()
```

Task arguments and return values must be primitives, lists, dicts, dataclasses or Documents, because each task is identified by a hash of its arguments. A scheduler job every minute resumes pipelines and tasks a restarted worker dropped.

### SSH

`SSHClient` pipes a script to `bash -s` on one host, or copies files with rsync, and streams the output as it arrives. A non-zero exit raises `SSHError` unless `check=False`, and a run past its timeout raises `SSHTimeoutError`.

```python
from cloudtoolkit.ssh.client import SSHClient, read_script
from cloudtoolkit.ssh.output_log import OutputLog

client = SSHClient(machine.address, private_key=machine.get_password("ssh_private_key"))
with OutputLog(machine, "setup_log") as log:
	client.run(read_script("cargo", "caddy", "install.sh", environment={"CADDYFILE": caddyfile}), on_output=log.write)
```

`OutputLog` keeps the output in the cache while the command runs, publishes it on the `ssh_output` realtime event, and stores it in the field once the command ends. A form reads it with `cloudtoolkit.ssh.output_log.get_live_output`. `wait_for_server` waits until SSH accepts one of the given users, and `create_keypair` makes an ed25519 keypair.

### Credits

Copied from the [Press Workflow Engine](https://github.com/frappe/press/tree/develop/press/workflow_engine) and its [`WorkflowBuilder`](https://github.com/frappe/press/blob/develop/press/workflow_engine/doctype/press_workflow/workflow_builder.py) in [frappe/press](https://github.com/frappe/press), renamed from Press Workflow to Pipeline and from `WorkflowBuilder` to `PipelineBuilder`.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/cloudtoolkit
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

agpl-3.0
