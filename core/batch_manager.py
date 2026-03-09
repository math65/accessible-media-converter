import os
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass

from core.conversion import ConversionTask, build_output_path


JOB_STATE_QUEUED = "queued"
JOB_STATE_RUNNING = "running"
JOB_STATE_DONE = "done"
JOB_STATE_SKIPPED = "skipped"
JOB_STATE_ERROR = "error"
JOB_STATE_STOPPED = "stopped"

SKIP_REASON_EXISTS = "exists"
SKIP_REASON_BATCH_STOPPED = "batch_stopped"


@dataclass
class BatchJob:
    index: int
    meta: object
    target_format: str
    settings: dict
    output_path: str | None
    weight: float
    state: str = JOB_STATE_QUEUED
    progress: int = 0
    skip_reason: str | None = None
    error_message: str = ""


class BatchConversionManager:
    def __init__(
        self,
        media_list,
        target_format,
        settings,
        output_dir=None,
        max_concurrent=2,
        output_policy="rename",
        continue_on_error=True,
        on_job_update=None,
        on_batch_update=None,
        on_batch_complete=None,
    ):
        self.media_list = list(media_list)
        self.target_format = target_format
        self.settings = dict(settings)
        self.output_dir = output_dir
        self.max_concurrent = max(1, int(max_concurrent))
        self.output_policy = output_policy
        self.continue_on_error = bool(continue_on_error)
        self.on_job_update = on_job_update
        self.on_batch_update = on_batch_update
        self.on_batch_complete = on_batch_complete

        self._state_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._active_tasks = {}
        self._controller_thread = None
        self._abort_new_jobs = False

        self.jobs = self._prepare_jobs()
        self.primary_output_dir = self._resolve_primary_output_dir()

    def start(self):
        if self._controller_thread and self._controller_thread.is_alive():
            return self._controller_thread
        self._controller_thread = threading.Thread(target=self._run, daemon=True, name="batch-conversion-manager")
        self._controller_thread.start()
        return self._controller_thread

    def stop(self):
        self._stop_requested.set()
        with self._state_lock:
            active_tasks = list(self._active_tasks.values())

        for task in active_tasks:
            task.stop()

    def _prepare_jobs(self):
        reserved_paths = set()
        jobs = []
        for index, meta in enumerate(self.media_list):
            base_output_path = build_output_path(meta.full_path, self.target_format, custom_output_dir=self.output_dir)
            resolved_output_path, skip_reason = self._reserve_output_path(
                base_output_path,
                reserved_paths,
            )
            job = BatchJob(
                index=index,
                meta=meta,
                target_format=self.target_format,
                settings=dict(self.settings),
                output_path=resolved_output_path,
                weight=self._get_job_weight(meta),
            )
            if skip_reason:
                job.state = JOB_STATE_SKIPPED
                job.progress = 100
                job.skip_reason = skip_reason
            jobs.append(job)
        return jobs

    def _reserve_output_path(self, base_output_path, reserved_paths):
        candidate_path = base_output_path
        suffix = 1

        while True:
            reserved_collision = self._path_key(candidate_path) in reserved_paths
            file_exists = os.path.exists(candidate_path)

            if not reserved_collision:
                if self.output_policy == "overwrite":
                    reserved_paths.add(self._path_key(candidate_path))
                    return candidate_path, None
                if not file_exists:
                    reserved_paths.add(self._path_key(candidate_path))
                    return candidate_path, None

            if self.output_policy == "skip":
                return None, SKIP_REASON_EXISTS

            candidate_path = self._append_suffix(base_output_path, suffix)
            suffix += 1

    def _resolve_primary_output_dir(self):
        if self.output_dir:
            return self.output_dir
        for job in self.jobs:
            if job.output_path:
                return os.path.dirname(job.output_path)
        return None

    def _run(self):
        runnable_jobs = [job for job in self.jobs if job.output_path]
        for job in self.jobs:
            self._emit_job_update(job)
        self._emit_batch_update()

        pending_jobs = list(runnable_jobs)
        active_futures = {}

        with ThreadPoolExecutor(max_workers=self.max_concurrent, thread_name_prefix="conversion-job") as executor:
            while pending_jobs or active_futures:
                while (
                    pending_jobs
                    and len(active_futures) < self.max_concurrent
                    and not self._stop_requested.is_set()
                    and not self._abort_new_jobs
                ):
                    job = pending_jobs.pop(0)
                    future = executor.submit(self._run_job, job)
                    active_futures[future] = job

                if not active_futures:
                    break

                done, _ = wait(list(active_futures.keys()), timeout=0.1, return_when=FIRST_COMPLETED)
                if not done:
                    continue

                for future in done:
                    job = active_futures.pop(future)
                    try:
                        result_state = future.result()
                    except Exception as exc:
                        job.error_message = str(exc)
                        self._set_job_state(job, JOB_STATE_ERROR, error_message=str(exc))
                        result_state = JOB_STATE_ERROR

                    if result_state == JOB_STATE_ERROR and not self.continue_on_error:
                        self._abort_new_jobs = True

            final_pending_reason = None
            final_pending_state = None
            if self._stop_requested.is_set():
                final_pending_state = JOB_STATE_STOPPED
            elif self._abort_new_jobs:
                final_pending_state = JOB_STATE_SKIPPED
                final_pending_reason = SKIP_REASON_BATCH_STOPPED

            while pending_jobs:
                job = pending_jobs.pop(0)
                self._set_job_state(job, final_pending_state, skip_reason=final_pending_reason)

        self._emit_batch_complete()

    def _run_job(self, job):
        task = ConversionTask(
            job.meta,
            job.target_format,
            job.settings,
            output_dir=self.output_dir,
            output_path=job.output_path,
        )
        with self._state_lock:
            self._active_tasks[job.index] = task

        self._set_job_state(job, JOB_STATE_RUNNING, progress=0)
        try:
            task.run(
                progress_callback=lambda pct: self._update_job_progress(job.index, pct),
                stop_check_callback=self._stop_requested.is_set,
            )
        except Exception as exc:
            if str(exc) == "Stopped by user" or self._stop_requested.is_set():
                self._set_job_state(job, JOB_STATE_STOPPED)
                return JOB_STATE_STOPPED

            self._set_job_state(job, JOB_STATE_ERROR, error_message=str(exc))
            return JOB_STATE_ERROR
        finally:
            with self._state_lock:
                self._active_tasks.pop(job.index, None)

        self._set_job_state(job, JOB_STATE_DONE, progress=100)
        return JOB_STATE_DONE

    def _update_job_progress(self, job_index, progress):
        progress = max(0, min(int(progress), 100))
        with self._state_lock:
            job = self.jobs[job_index]
            if job.state != JOB_STATE_RUNNING:
                return
            job.progress = progress
            event = self._build_job_event(job)
            summary = self._build_summary()

        self._dispatch_job_update(event)
        self._dispatch_batch_update(summary)

    def _set_job_state(self, job, state, progress=None, skip_reason=None, error_message=None):
        if state is None:
            return

        with self._state_lock:
            job.state = state
            if progress is not None:
                job.progress = max(0, min(int(progress), 100))
            elif state in (JOB_STATE_DONE, JOB_STATE_SKIPPED, JOB_STATE_ERROR):
                job.progress = 100
            job.skip_reason = skip_reason
            if error_message:
                job.error_message = error_message
            event = self._build_job_event(job)
            summary = self._build_summary()

        self._dispatch_job_update(event)
        self._dispatch_batch_update(summary)

    def _emit_job_update(self, job):
        with self._state_lock:
            event = self._build_job_event(job)
        self._dispatch_job_update(event)

    def _emit_batch_update(self):
        with self._state_lock:
            summary = self._build_summary()
        self._dispatch_batch_update(summary)

    def _emit_batch_complete(self):
        with self._state_lock:
            summary = self._build_summary()
        summary["user_stopped"] = self._stop_requested.is_set()
        summary["aborted_after_error"] = self._abort_new_jobs and not self._stop_requested.is_set()
        if self.on_batch_complete:
            self.on_batch_complete(summary)

    def _dispatch_job_update(self, event):
        if self.on_job_update:
            self.on_job_update(event)

    def _dispatch_batch_update(self, summary):
        if self.on_batch_update:
            self.on_batch_update(summary)

    def _build_job_event(self, job):
        return {
            "index": job.index,
            "state": job.state,
            "progress": job.progress,
            "skip_reason": job.skip_reason,
            "error_message": job.error_message,
            "output_path": job.output_path,
        }

    def _build_summary(self):
        counts = {
            JOB_STATE_QUEUED: 0,
            JOB_STATE_RUNNING: 0,
            JOB_STATE_DONE: 0,
            JOB_STATE_SKIPPED: 0,
            JOB_STATE_ERROR: 0,
            JOB_STATE_STOPPED: 0,
        }
        total_weight = 0.0
        accumulated_progress = 0.0

        for job in self.jobs:
            counts[job.state] = counts.get(job.state, 0) + 1
            weight = job.weight
            total_weight += weight
            accumulated_progress += weight * job.progress

        overall_progress = 0
        if total_weight > 0:
            overall_progress = int(accumulated_progress / total_weight)

        return {
            "total": len(self.jobs),
            "queued": counts[JOB_STATE_QUEUED],
            "running": counts[JOB_STATE_RUNNING],
            "done": counts[JOB_STATE_DONE],
            "skipped": counts[JOB_STATE_SKIPPED],
            "error": counts[JOB_STATE_ERROR],
            "stopped": counts[JOB_STATE_STOPPED],
            "overall_progress": max(0, min(overall_progress, 100)),
            "primary_output_dir": self.primary_output_dir,
        }

    @staticmethod
    def _get_job_weight(meta):
        try:
            duration = float(getattr(meta, "duration", 0.0) or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        return duration if duration > 0 else 1.0

    @staticmethod
    def _path_key(path):
        return os.path.normcase(os.path.abspath(path))

    @staticmethod
    def _append_suffix(path, suffix):
        root, ext = os.path.splitext(path)
        return f"{root} ({suffix}){ext}"
