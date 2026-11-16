app_name = "cloudtoolkit"
app_title = "Cloud Toolkit"
app_publisher = "Frappe"
app_description = "Shared building blocks for Frappe Cloud apps"
app_email = "developers@frappe.io"
app_license = "agpl-3.0"

use_json_request_body = True
export_python_type_annotations = True
require_type_annotated_api_methods = True

before_install = "cloudtoolkit.install.before_install"

scheduler_events = {
	"cron": {
		"* * * * *": [
			"cloudtoolkit.pipeline.doctype.pipeline.pipeline.retry_pipelines",
			"cloudtoolkit.pipeline.doctype.pipeline.pipeline.retry_pipeline_callbacks",
			"cloudtoolkit.pipeline.doctype.pipeline_task.pipeline_task.retry_tasks",
		],
	},
}
