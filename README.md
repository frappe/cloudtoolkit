### Pipeline

Durable step-by-step pipelines for Frappe documents

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app pipeline
```

Add `required_apps = ["pipeline"]` to the hooks of an app that uses it.

### Usage

A pipeline runs the `@task` steps of a `@flow` method in background jobs. Each finished step is stored, so a retried or restarted pipeline skips the steps that already ran.

```python
from pipeline.pipeline.doctype.pipeline.decorators import flow, task
from pipeline.pipeline.doctype.pipeline.pipeline_builder import PipelineBuilder


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

The engine comes from [frappe/press](https://github.com/frappe/press).

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/pipeline
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

agpl-3.0
