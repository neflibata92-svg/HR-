"""常驻 Agent 单周期编排。"""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, Thread
from time import monotonic, sleep
from typing import Any

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings


class ResidentAgent:
    def __init__(
        self,
        settings: AgentSettings,
        api: ApiClient,
        *,
        run_task: Callable[[dict[str, Any]], Any],
        poll_resumes: Callable[[], Any],
        check_login_status: Callable[[], str],
        sleep: Callable[[float], Any] = sleep,
    ) -> None:
        self.settings = settings
        self.api = api
        self._run_task = run_task
        self._poll_resumes = poll_resumes
        self._check_login_status = check_login_status
        self._sleep = sleep

    def _heartbeat_until_sent(self, status: str, **payload: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                return self.api.heartbeat(status, **payload)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._sleep(0.2)
        assert last_error is not None
        raise last_error

    def _run_with_heartbeat(self, task: dict[str, Any], login_status: str) -> None:
        stopped = Event()

        def keep_alive() -> None:
            interval = max(0.01, min(float(self.settings.poll_interval_seconds), 10.0))
            next_attempt = monotonic() + interval
            while not stopped.wait(max(0.0, next_attempt - monotonic())):
                try:
                    self.api.heartbeat(
                        "running",
                        availability="busy",
                        current_task_id=int(task["id"]),
                        current_job_id=int(task["job_id"]),
                        boss_login_status=login_status,
                        last_error="",
                    )
                except Exception:  # noqa: BLE001
                    pass
                next_attempt += interval

        thread = Thread(target=keep_alive, daemon=True)
        thread.start()
        try:
            self._run_task(task)
        finally:
            stopped.set()
            thread.join(timeout=max(0.1, float(self.settings.poll_interval_seconds)))
            try:
                self._heartbeat_until_sent(
                    "idle",
                    availability="idle",
                    current_task_id=None,
                    current_job_id=None,
                    boss_login_status=login_status,
                    last_error="",
                )
            except Exception:  # noqa: BLE001
                pass

    def run_cycle(self) -> None:
        login_status = self._check_login_status()
        run = self.api.heartbeat(
            "idle",
            availability="idle" if login_status == "logged_in" else "offline",
            boss_login_status=login_status,
            last_error="",
        )
        task_id = run.get("current_task_id")
        if task_id is not None and login_status == "logged_in":
            task = self.api.get_task(int(task_id))
            if task.get("status") == "ready":
                task = self.api.claim_task(int(task_id))
            if task.get("status") == "running":
                self.api.heartbeat(
                    "running",
                    availability="busy",
                    current_task_id=int(task["id"]),
                    current_job_id=int(task["job_id"]),
                    boss_login_status=login_status,
                    last_error="",
                )
                self._run_with_heartbeat(task, login_status)
        self._poll_resumes()

    def run_forever(self, *, stop_after_cycles: int | None = None) -> None:
        cycles = 0
        while stop_after_cycles is None or cycles < stop_after_cycles:
            self.run_cycle()
            cycles += 1
            if stop_after_cycles is not None and cycles >= stop_after_cycles:
                return
            self._sleep(self.settings.poll_interval_seconds)
