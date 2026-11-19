### Cloud Toolkit

Shared building blocks for Frappe Cloud apps: durable pipelines, SSH, and TLS certificates.

### Installation

You can install this app using the [Pilot](https://github.com/frappe/pilot) CLI:

```bash
pilot -b $BENCH_NAME get-app https://github.com/frappe/cloudtoolkit --branch develop
pilot -b $BENCH_NAME install-app $SITE_NAME cloudtoolkit
```

Add `required_apps = ["cloudtoolkit"]` to the hooks of an app that uses it.

This app was named `pipeline`. Installing it on a site that has `pipeline` takes over the `Pipeline` module, so its tables and rows stay, and drops `pipeline` from the installed apps. Keep the `pipeline` checkout on the bench until every site has this app, and never run `uninstall-app pipeline`: it deletes the Pipeline tables.

### Tools

| Tool | What it does |
| --- | --- |
| [Pipeline](cloudtoolkit/pipeline/README.md) | Durable step-by-step flows on a document, run in background jobs and resumed after restarts. |
| [SSH](cloudtoolkit/ssh/README.md) | Run scripts and rsync files over SSH, and stream the output into a document field. |
| [TLS](cloudtoolkit/tls/README.md) | Issue Let's Encrypt certificates through the dns-01 challenge. |

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
