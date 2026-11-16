from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from cloudtoolkit.ssh.output_log import OutputLog, get_live_output, live_output


class IntegrationTestOutputLog(IntegrationTestCase):
	"""How a command's output reaches its document, while it runs and once it ends."""

	def todo(self) -> Document:
		todo = frappe.get_doc({"doctype": "ToDo", "description": "the last run's log"}).insert()
		return todo

	def test_a_run_does_not_write_the_document_until_it_ends(self):
		"""A write would lock the row for the whole run, and block a stop request."""
		todo = self.todo()

		with patch.object(type(todo), "db_set") as db_set, OutputLog(todo, "description") as log:
			log.write("step one\n")
			db_set.assert_not_called()

		db_set.assert_called_once_with("description", "step one\n", update_modified=False)

	def test_a_new_run_hides_the_last_runs_log(self):
		todo = self.todo()

		with OutputLog(todo, "description"):
			self.assertEqual(live_output(todo, "description"), "")

	def test_an_appending_run_keeps_the_last_runs_log(self):
		todo = self.todo()

		with OutputLog(todo, "description", append=True) as log:
			log.write("\nmore")

		self.assertEqual(frappe.db.get_value("ToDo", todo.name, "description"), "the last run's log\nmore")

	def test_live_output_is_read_while_the_run_is_going(self):
		todo = self.todo()

		with OutputLog(todo, "description", flush_seconds=0) as log:
			log.write("halfway")
			self.assertEqual(get_live_output("ToDo", todo.name, "description"), "halfway")

	def test_live_output_needs_a_real_field(self):
		with self.assertRaises(frappe.ValidationError):
			get_live_output("ToDo", self.todo().name, "no_such_field")
