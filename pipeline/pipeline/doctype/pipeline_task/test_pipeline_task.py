# Copyright (c) 2026, frappe and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from pipeline.pipeline.doctype.pipeline_task.pipeline_task import retry_tasks

ENQUEUE = "pipeline.pipeline.doctype.pipeline_task.pipeline_task.enqueue_task"


class IntegrationTestPipelineTask(IntegrationTestCase):
	"""Picking up work a restarted worker dropped."""

	def setUp(self):
		frappe.set_user("Administrator")

	def pipeline(self) -> str:
		"""A pipeline waiting on a task. `linked_docname` is a real row, as the engine
		resolves it before running anything."""
		with patch("pipeline.pipeline.doctype.pipeline.pipeline.enqueue_pipeline"):
			return (
				frappe.get_doc(
					{
						"doctype": "Pipeline",
						"linked_doctype": "User",
						"linked_docname": "Administrator",
						"main_method_name": "run_build",
						"main_method_title": "Run Build",
						"status": "Running",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

	def task(self, status: str) -> str:
		"""A task row in one state, without running it."""
		with patch(ENQUEUE):
			return (
				frappe.get_doc(
					{
						"doctype": "Pipeline Task",
						"pipeline": self.pipeline(),
						"method_name": "run_provision_script",
						"method_title": "Run Provision Script",
						"signature": frappe.generate_hash(length=16),
						"status": status,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

	def test_a_task_a_restarted_worker_dropped_is_enqueued_again(self):
		"""Its job died with the worker, so nothing else will ever run it. The pipeline
		waiting on it stays Running until this puts it back."""
		name = self.task("Running")

		with patch(ENQUEUE) as enqueue:
			retry_tasks()

		self.assertIn(name, [call.args[0] for call in enqueue.call_args_list])

	def test_a_task_still_waiting_for_a_worker_is_enqueued_again(self):
		"""Queued with no job behind it is the same problem, one step earlier."""
		name = self.task("Queued")

		with patch(ENQUEUE) as enqueue:
			retry_tasks()

		self.assertIn(name, [call.args[0] for call in enqueue.call_args_list])

	def test_a_finished_task_is_left_alone(self):
		"""Re-running one would repeat whatever it already did."""
		done = self.task("Success")
		failed = self.task("Failure")

		with patch(ENQUEUE) as enqueue:
			retry_tasks()

		asked = [call.args[0] for call in enqueue.call_args_list]
		self.assertNotIn(done, asked)
		self.assertNotIn(failed, asked)
