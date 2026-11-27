from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from cloudtoolkit.pipeline.doctype.pipeline.exceptions import PipelineWaitTimeoutError
from cloudtoolkit.pipeline.doctype.pipeline.pipeline_builder import PipelineBuilder
from cloudtoolkit.pipeline.doctype.pipeline_task.test_pipeline_task import PipelineTaskFixtures


class IntegrationTestWait(PipelineTaskFixtures, IntegrationTestCase):
	"""A bounded defer, timed from the current task's first run."""

	def setUp(self):
		frappe.set_user("Administrator")

	def builder(self, started_seconds_ago: int) -> PipelineBuilder:
		task = self.task("Running")
		creation = frappe.utils.add_to_date(None, seconds=-started_seconds_ago)
		frappe.db.set_value("Pipeline Task", task, "creation", creation, update_modified=False)

		builder = PipelineBuilder({"doctype": "User"})
		builder.flags.current_pipeline_task = task
		return builder

	def test_a_step_within_its_wait_is_deferred(self):
		with patch.object(PipelineBuilder, "defer_current_task") as defer:
			self.builder(started_seconds_ago=60).wait("Still booting.", for_=900)

		defer.assert_called_once_with("Still booting.")

	def test_a_step_past_its_wait_fails(self):
		with (
			patch.object(PipelineBuilder, "defer_current_task") as defer,
			self.assertRaisesRegex(PipelineWaitTimeoutError, "Still booting."),
		):
			self.builder(started_seconds_ago=1000).wait("Still booting.", for_=900)

		defer.assert_not_called()
