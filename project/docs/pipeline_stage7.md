# Stage 7: Windows background operation

The approved production task runs the existing `run_system.py` launcher through the same virtual environment's `pythonw.exe`. It starts automatically after this Windows user signs in, without a terminal or browser. A 30-second sign-in trigger and a one-minute recovery trigger use the same task. This is a Task Scheduler task, not a Windows Service. It does not run before sign-in or while the PC is asleep; no password, elevated account or power-policy change is stored.

Production uses `project/incoming/bangladesh`, `project/output/bangladesh`, `project/runtime/state` and `project/runtime/artifacts`. The previous 20-file demonstration queue is retained in its original report folders and is not migrated into production. Existing output workbooks remain untouched; normal collision-safe versioning still applies.

## Commands

Run from the repository root using the installed environment:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --startup status
project/.venv/Scripts/python.exe project/run_system.py --startup start
project/.venv/Scripts/python.exe project/run_system.py --startup stop
~~~

For a new installation:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --startup install
project/.venv/Scripts/python.exe project/run_system.py --startup start
~~~

Installation does not overwrite an existing task. Its one-minute recovery trigger can start it automatically; use start for immediate launch. `--config` selects a different configuration and `--port` sets the port saved at installation. Always use the same config for later management. Use `status` to inspect the saved program, arguments, account, working directory and restart policy. Existing tasks are not silently changed by passing a new port to `start`. Start also re-enables automatic startup after a prior stop.

`stop` first disables automatic task triggers, then sends a native Windows event to the background process. Intake and new claims stop, the current invoice is allowed to finish, prepared publication follows normal recovery, and the process exits normally. A stop request is not proof that shutdown has finished: wait for the task to stop running and for the log to report normal exit. Its disabled state is retained. A long vision request can still take its existing two-hour allowance. Stop remains in effect across sign-in until you use start again.

To remove automatic startup, stop it and wait for exit, then run:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --startup uninstall
~~~

Uninstall refuses a running task. It removes only the matching FOC task and preserves all files/data. After removal the original foreground command still works:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

Do not run foreground and background launchers at the same time on the same configuration/port. Task Scheduler ignores another start while running; native scanner/worker locks and an additional background log lock prevent duplicate ownership. A task name is derived from the absolute state directory; preserve that configuration when managing it.

## Failure restart and dependencies

A native trigger checks every minute. IgnoreNew means a running task is left alone; an exited/crashed pipeline starts again while automatic startup is enabled. The native failure setting additionally retries launch failures three times. A forced-process test on this PC showed that the failure setting alone did not restart an exited program, so the periodic recovery trigger is required. It has no maximum execution duration, so an idle pipeline or lengthy invoice is not ended by the scheduler's default time limit. A graceful stop disables those triggers and remains stopped. Persistent startup failures will be retried by the one-minute trigger; use stop to disable it while repairing the cause. Forced Windows termination/logoff/power loss uses the existing interrupted-attempt recovery; it is not a graceful stop.

Ollama already has a Windows sign-in startup entry under this PC's current user. Stage 7 does not create a second Ollama server, install models, alter existing startup entries or change generation limits. `/api/ollama` and System status report model availability independently of scanner/worker health. OCR-only work can continue when the image reader is unavailable; source values needing the model may remain blank under existing rules. Restore Ollama/model availability before retrying those PDFs.

Closing the browser does not stop the task. A paused queue is different from a stopped task; its policy persists across restarts. Missing inboxes, model availability, failed components and current activity retain their existing independent dashboard states. Open http://127.0.0.1:8080/ when needed; no LAN access is added.

## Logs and backups

Background Python output is written to `project/runtime/state/logs/system.log`. It rotates at approximately 5 MiB with three backups. These logs include operational paths and shipment diagnostics; protect them as local project data. Standard output is recorded at INFO and standard-error diagnostics at WARNING; actual pipeline exceptions are logged at ERROR with a traceback. Native-library output written directly to operating-system handles may not appear in these Python logs. Foreground execution retains its existing terminal output.

Before upgrading code, gracefully stop the task and wait for completion. Back up the SQLite database plus managed input/attempt artifacts and published output together. Do not copy only the database or move paths recorded in historical attempts. Restore matching code/schema/data as a unit. Logs are useful support records but are not substitutes for retained invoice evidence. No automatic evidence deletion is enabled.

The launcher, account, Python environment, model cache and managed directories must remain accessible at their recorded absolute paths. After moving the installed project, stop/uninstall the old task and install deliberately from the new location after a planned data migration. See [operations](operations.md), [build/rollback](build.md), and [data/evidence](data-and-evidence.md).

## Acceptance

Automated and local Task Scheduler checks are recorded under `project/reports/pipeline_stage7_20261021`. A real sign-out/reboot is intentionally deferred to Stage 8 with user coordination; sign-in trigger registration alone does not prove reboot acceptance. This stage does not claim unseen-PDF extraction accuracy.

Native behavior references: [Task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset) and [Task security contexts](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks).
