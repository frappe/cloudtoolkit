from __future__ import annotations

import time
import typing

import frappe
from frappe import _

if typing.TYPE_CHECKING:
	from frappe.model.document import Document

EVENT = "ssh_output"
FLUSH_SECONDS = 3
CACHE_SECONDS = 15 * 60


class OutputLog:
	"""Streams a command's output into a document field while it runs. The cache holds it until
	the run ends, so the run never locks the row."""

	def __init__(
		self,
		document: Document,
		fieldname: str,
		event: str = EVENT,
		flush_seconds: int = FLUSH_SECONDS,
		append: bool = False,
	) -> None:
		self.document = document
		self.fieldname = fieldname
		self.event = event
		self.flush_seconds = flush_seconds
		self.append = append
		self.lines: list[str] = []
		self.published = 0
		self.flushed_at = time.monotonic()

	def __enter__(self) -> OutputLog:
		"""This run owns the field, unless it is adding to what an earlier one left."""
		if self.append:
			self.lines = [live_output(self.document, self.fieldname)]
			return self

		frappe.cache.set_value(self.cache_key, "", expires_in_sec=CACHE_SECONDS)
		return self

	def __exit__(self, *exception: object) -> None:
		self.flush()
		self.store()

	def write(self, text: str) -> None:
		self.lines.append(text)
		if time.monotonic() - self.flushed_at >= self.flush_seconds:
			self.flush()

	@property
	def cache_key(self) -> str:
		return get_cache_key(self.document.doctype, self.document.name, self.fieldname)

	def flush(self) -> None:
		if len(self.lines) == self.published:
			return

		self.published = len(self.lines)
		self.flushed_at = time.monotonic()
		text = "".join(self.lines)
		frappe.cache.set_value(self.cache_key, text, expires_in_sec=CACHE_SECONDS)
		frappe.publish_realtime(
			self.event,
			{"name": self.document.name, "fieldname": self.fieldname, "value": text},
			doctype=self.document.doctype,
			docname=self.document.name,
		)

	def store(self) -> None:
		"""The run is over, so the document takes over from the cache."""
		self.document.db_set(self.fieldname, "".join(self.lines), update_modified=False)
		frappe.cache.delete_value(self.cache_key)


def get_cache_key(doctype: str, name: str, fieldname: str) -> str:
	return f"ssh_output:{doctype}:{name}:{fieldname}"


def live_output(document: Document, fieldname: str) -> str:
	"""What a command has printed so far: the cache while it runs, the field once it ends."""
	live = frappe.cache.get_value(get_cache_key(document.doctype, document.name, fieldname))
	return live if live is not None else (document.get(fieldname) or "")


@frappe.whitelist()
def get_live_output(doctype: str, name: str, fieldname: str) -> str:
	"""`live_output` for any document the user can read, so no doctype needs an endpoint of its own."""
	document = frappe.get_doc(doctype, name)
	document.check_permission("read")

	if not document.meta.has_field(fieldname):
		frappe.throw(_("{0} has no field {1}.").format(doctype, fieldname))
	if not document.has_permlevel_access_to(fieldname):
		frappe.throw(_("You cannot read {0} of {1}.").format(fieldname, doctype), frappe.PermissionError)

	return live_output(document, fieldname)
