# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations


class PipelineTaskEnqueued(Exception):
	"""Raised when a task is enqueued and the flow needs to be paused."""

	def __init__(self, message: str, pipeline_name: str, task_name: str | None = None):
		super().__init__(message)
		self.pipeline_name = pipeline_name
		self.task_name = task_name


class PipelineRunningError(Exception):
	"""Raised when trying to get result of a running or queued pipeline."""

	pass


class PipelineFailedError(Exception):
	"""Raised when the pipeline failed but no exception was recorded."""

	pass


class PipelineFatalError(Exception):
	"""Raised when the pipeline encountered a fatal error."""

	def __init__(self, message: str, traceback: str | None = None):
		super().__init__(message)
		self.traceback = traceback
