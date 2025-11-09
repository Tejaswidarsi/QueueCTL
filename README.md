# QueueCTL — Lightweight Job Queue CLI

_A minimal command-line tool to enqueue, process, and manage background jobs — built for simplicity, learning, and reliability._

---

## 1. Setup Instructions

### **Prerequisites**
- Python 3.8+
- Windows PowerShell or Command Prompt

### Run Help
```
python queuectl.py --help
```
----

## 2. Usage Examples

### i) Enqueue a Job
```
PowerShell (Windows):

python queuectl.py enqueue '{ "id": "job1", "command": "echo Hello from Windows with spaces and stuff!" }'
```
```
Command Prompt (cmd):

python queuectl.py enqueue "{\"id\": \"job1\", \"command\": \"echo Hello from Windows with spaces and stuff!\"}"
```


Or enqueue from a JSON file:

python queuectl.py enqueue job1.json

```
Example job1.json:

{
  "id": "job1",
  "command": "echo Hello from QueueCTL"
}
```
_ouput_
```
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[queuectl] Initializing database...
[queuectl] Database ready: C:\Users\HP\Desktop\flam\queuectl.db
C:\Users\HP\Desktop\flam\queuectl.py:98: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  now = datetime.datetime.utcnow().isoformat() + "Z"
enqueued job job1
```
### ii) List Jobs
_cmd_
```
python queuectl.py list
```
_output_
```
{"id": "Job2", "command": "echo Hello from Windows with spaces and stuff!", "state": "completed", "attempts": 1, "max_retries": 3, "next_run": 0, "updated_at": "2025-11-09T14:52:42.080310Z"}
{"id": "Job3", "command": "echo 'Backend'", "state": "completed", "attempts": 1, "max_retries": 3, "next_run": 0, "updated_at": "2025-11-09T15:17:12.554503Z"}
```
Filter by state:
```
python queuectl.py list --state pending
python queuectl.py list --state processing
python queuectl.py list --state dead
```
### iii). workers to process queued jobs
_cmd_
```
python queuectl.py worker start --count 3

Press Ctrl + C to stop workers gracefully.
```
_output_
```
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[queuectl] Initializing database...
[queuectl] Database ready: C:\Users\HP\Desktop\flam\queuectl.db
starting 3 worker(s)...
started 3 worker processes
[worker 12344] claimed job=retry-demo attempts=1/4 cmd=exit 77
[worker 12344] job retry-demo failed (code 77):
[worker 12344] claimed job=retry-demo attempts=2/4 cmd=exit 77
[worker 12356] claimed job=stress-1 attempts=1/3 cmd=exit 1
[worker 12356] job stress-1 failed (code 1):
[worker 12368] claimed job=stress-2 attempts=1/3 cmd=exit 1
[worker 12344] job retry-demo failed (code 77):
[worker 12344] → retry in 4 seconds (backoff 2^2)
[worker 12356] → retry in 2 seconds
[worker 12368] → retry in 2 seconds
[worker 12344] claimed job=retry-demo attempts=3/4 cmd=exit 77
[worker 12344] job retry-demo failed (code 77):
[worker 12344] → retry in 8 seconds (backoff 2^3)
[worker 12356] claimed job=stress-1 attempts=2/3 ...
[worker 12356] job stress-1 failed → retry in 4s
...
[worker 12344] claimed job=retry-demo attempts=4/4 cmd=exit 77
[worker 12344] job retry-demo failed → MAX RETRIES EXCEEDED → MOVED TO DLQ
[worker 12344] graceful shutdown triggered.
[worker 12356] graceful shutdown triggered.
[worker 12368] graceful shutdown triggered.
parent received interrupt, stopping workers...
workers stopped
```
### iv) Status
_cmd_
```
python queuectl.py status
```
_output_
```
Shows the number of jobs in each state and active worker count.
[queuectl] Initializing database...
[queuectl] Database ready: C:\Users\HP\Desktop\flam\queuectl.db
job states summary:
  pending: 0
  processing: 1
  completed: 3
  failed: 0
  dead: 4
active local worker processes: 0
```

### v) Dead Letter Queue (DLQ)
# List failed jobs
```
python queuectl.py dlq list
```
# Retry a failed job
```
python queuectl.py dlq retry job1
```
### vi) Demo Mode
_cmd_
```
python queuectl.py demo
```
_output_
```
Runs a quick demo: enqueues 3 jobs and starts a worker that processes them for 6 seconds.
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[queuectl] Initializing database...
[queuectl] Database ready: C:\Users\HP\Desktop\flam\queuectl.db
C:\Users\HP\Desktop\flam\queuectl.py:98: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  now = datetime.datetime.utcnow().isoformat() + "Z"
starting 2 worker(s)...
started 2 worker processes
demo: workers running for 8 seconds...
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[worker 16100] claimed job=demo-ok attempts=1/2 cmd=echo demo ok
[worker 20148] claimed job=demo-ok attempts=1/2 cmd=echo demo ok
[worker 16100] job demo-ok completed: stdout=demo ok
[worker 20148] job demo-ok completed: stdout=demo ok
[worker 16100] claimed job=demo-sleep attempts=1/1 cmd=sleep 2 && echo slept
[worker 16100] job demo-sleep failed (code 1): 'sleep' is not recognized as an internal or external command,
operable program or batch file.
stopping workers gracefully...
[worker 20148] graceful shutdown triggered.
[worker 16100] graceful shutdown triggered.
workers stopped
demo finished. Status:
job states summary:
  pending: 0
  processing: 1
  completed: 3
  failed: 0
  dead: 4
active local worker processes: 0
```
### vii) Configuration
_cmd_
```
python queuectl.py worker start --count 3
```
_output_
```
[DEBUG] Using database: C:\Users\HP\Desktop\flam\queuectl.db
[queuectl] Initializing database...
[queuectl] Database ready: C:\Users\HP\Desktop\flam\queuectl.db
starting 3 worker(s)...
started 3 worker processes
[worker 12344] claimed job=retry-demo attempts=1/4 cmd=exit 77
[worker 12344] job retry-demo failed (code 77):
[worker 12344] claimed job=retry-demo attempts=2/4 cmd=exit 77
[worker 12356] claimed job=stress-1 attempts=1/3 cmd=exit 1
[worker 12356] job stress-1 failed (code 1):
[worker 12368] claimed job=stress-2 attempts=1/3 cmd=exit 1
[worker 12344] job retry-demo failed (code 77):
[worker 12344] → retry in 4 seconds (backoff 2^2)
[worker 12356] → retry in 2 seconds
[worker 12368] → retry in 2 seconds
[worker 12344] claimed job=retry-demo attempts=3/4 cmd=exit 77
[worker 12344] job retry-demo failed (code 77):
[worker 12344] → retry in 8 seconds (backoff 2^3)
[worker 12356] claimed job=stress-1 attempts=2/3 ...
[worker 12356] job stress-1 failed → retry in 4s
...
[worker 12344] claimed job=retry-demo attempts=4/4 cmd=exit 77
[worker 12344] job retry-demo failed → MAX RETRIES EXCEEDED → MOVED TO DLQ
[worker 12344] graceful shutdown triggered.
[worker 12356] graceful shutdown triggered.
[worker 12368] graceful shutdown triggered.
parent received interrupt, stopping workers...
workers stopped
```
-----
## 3. Architecture Overview
Job Lifecycle:

* Enqueue: A job JSON is added to the queue (pending state).

* Processing: A worker picks up the job and executes the command.

* Success: Job moves to completed.

* Failure: Failed jobs retry automatically (up to max_retries) or move to DLQ.

Persistence

Jobs are stored locally (e.g., SQLite/JSON file depending on implementation).
Workers continuously poll the queue, execute commands, and update states.

Worker Logic

Each worker:

* Fetches a pending job.

* Runs the command specified.

* Updates the job’s status.

* Retries failed jobs automatically up to a limit.
  -----
 ## 4. Assumptions & Trade-offs
<marquee behavior="scroll" direction="left" scrollamount="5">

<table>
  <tr>
    <th>Aspect</th>
    <th>Decision</th>
    <th>Rationale</th>
  </tr>
  <tr>
    <td>Data Storage</td>
    <td>Local JSON/SQLite</td>
    <td>Keeps setup lightweight and portable</td>
  </tr>
  <tr>
    <td>Execution</td>
    <td>OS command via subprocess</td>
    <td>Allows simple command-based jobs</td>
  </tr>
  <tr>
    <td>Concurrency</td>
    <td>Thread-based workers</td>
    <td>Easy to scale for basic use cases</td>
  </tr>
  <tr>
    <td>Retries</td>
    <td>Fixed max retries</td>
    <td>Simplicity over dynamic policy</td>
  </tr>
  <tr>
    <td>Platform</td>
    <td>Windows-compatible CLI</td>
    <td>Avoids shell escape issues</td>
  </tr>
</table>

</marquee>

-----

# Author
_Tejaswi Darsi_
_B.Tech CSE | Frontend & AI Enthusiast_
_Guntur, Andhra Pradesh_
  
