### Pipeline

A pipeline runs the `@task` steps of a `@flow` method in background jobs. Each finished step is stored, so a retried or restarted pipeline skips the steps that already ran.

### Usage

Subclass `PipelineBuilder` in the controller of the doctype that owns the work. Mark the entry method with `@flow` and each step it calls with `@task`.

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
		"""Provision a server"""
		if not self.is_ready():
			self.defer_current_task("Server is still booting.")
		return "server-1"

	@task(queue="long", timeout=3600)
	def build(self, server: str): ...

	def on_pipeline_success(self, pipeline): ...

	def on_pipeline_failure(self, pipeline): ...
```

Start it with `run_as_pipeline`, which inserts a `Pipeline` document and returns its name:

```python
pipeline_name = frappe.get_doc("Deploy Request", name).deploy.run_as_pipeline()
```

Calling `deploy()` directly runs every step inline, with no Pipeline document.

### How it runs

- `run_as_pipeline` reads the `self.*` calls in the flow's source and records them as the pipeline's steps. A task's title is the first line of its docstring, or its name in title case.
- Each `@task` call becomes a `Pipeline Task` job. The flow stops there and runs again from the top once the task ends; finished tasks return their stored result instead of running again.
- A task is identified by a hash of its method and arguments, so arguments must be primitives, lists, tuples, sets, dicts, dataclasses or Documents. Call `self.step.with_task_id("...")(...)` to run the same step twice with the same arguments.
- Return values that are not JSON are pickled into a `Pipeline Object`. Keep their classes importable at the same path until the pipeline ends.
- `defer_current_task(message)` puts the current task back in the queue, for polling until something is ready.
- `wait(message, for_)` defers the same way, but raises `PipelineWaitTimeoutError` once the current task has waited `for_` seconds since it first ran. `step_started` is that first run.
- `on_pipeline_success(pipeline)` or `on_pipeline_failure(pipeline)` runs on the linked document once the pipeline ends. A failing callback is retried with backoff.
- Scheduler jobs every minute resume pipelines, tasks and callbacks that a restarted worker dropped.

### State and results

- `self.kv` is a key-value store scoped to the pipeline run, with `set`, `get` and `delete`. Outside a pipeline it is in memory.
- `frappe.get_doc("Pipeline", name).get_result()` returns the flow's return value, re-raises its exception, or raises `PipelineRunningError` while it runs.
- `Pipeline.force_fail()` asks a running pipeline to stop at its next step.
- Deleting a document deletes its finished pipelines, and is refused while one is running.

### Helpers

`deadlock_retry(times)` runs a step again when MariaDB picks it as a deadlock victim. Use it only for work that is safe to repeat, and put it under `@task`:

```python
from cloudtoolkit.pipeline.utils import deadlock_retry


@task
@deadlock_retry(times=3)
def update_status(self): ...
```

### Tests

Under `frappe.flags.in_test`, pipelines and tasks run in the foreground and callbacks run inline, so a test can start a pipeline and assert on the result straight after. Set `LOG_PIPELINE_DEBUG_INFO=1` to print each job as it runs.
