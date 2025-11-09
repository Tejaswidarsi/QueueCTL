import os
import sys
import json
import sqlite3
import time
import datetime
import subprocess
import signal
import threading
from multiprocessing import Process, Event
import uuid
import click
from pathlib import Path

DB_PATH = str(Path.cwd() / "queuectl.db")
print(f"[DEBUG] Using database: {DB_PATH}", file=sys.stderr)
if not os.access(Path.cwd(), os.W_OK):
    print("[ERROR] Current directory is not writable!", file=sys.stderr)
    sys.exit(1)
DEFAULT_CONFIG = {"max_retries": 3, "backoff_base": 2}

# ---------- DB helpers ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        command TEXT NOT NULL,
        state TEXT NOT NULL,
        attempts INTEGER NOT NULL,
        max_retries INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        next_run INTEGER DEFAULT 0,
        last_error TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    for k,v in DEFAULT_CONFIG.items():
        cur.execute("INSERT OR IGNORE INTO config(key,value) VALUES (?,?)", (k, json.dumps(v)))
    conn.commit()
    conn.close()

def get_config(key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    r = cur.fetchone()
    conn.close()
    return json.loads(r["value"]) if r else None

def set_config(key, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO config(key,value) VALUES (?,?)", (key, json.dumps(value)))
    conn.commit()
    conn.close()

# ---------- Job management ----------
def enqueue_job(job_json_str):
    try:
        job = json.loads(job_json_str)
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON") from e

    if "id" not in job:
        job["id"] = str(uuid.uuid4())
    if "command" not in job:
        raise ValueError("job must contain 'command'")

    now = datetime.datetime.utcnow().isoformat() + "Z"
    attempts = int(job.get("attempts", 0))
    max_retries = int(job.get("max_retries", get_config("max_retries")))
    state = job.get("state", "pending")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
      INSERT OR REPLACE INTO jobs (id,command,state,attempts,max_retries,created_at,updated_at,next_run)
      VALUES (?,?,?,?,?,?,?,?)
    """, (job["id"], job["command"], state, attempts, max_retries, now, now, 0))
    conn.commit()
    conn.close()
    return job["id"]

def list_jobs(state=None):
    conn = get_conn()
    cur = conn.cursor()
    if state:
        cur.execute("SELECT * FROM jobs WHERE state=? ORDER BY created_at", (state,))
    else:
        cur.execute("SELECT * FROM jobs ORDER BY created_at")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- Atomic claim ----------
def claim_job_atomic():
    """
    Atomically claim a single pending job whose next_run <= now.
    The claim increments attempts and sets state=processing and updated_at.
    Returns job row as dict or None if none available.
    """
    conn = get_conn()
    cur = conn.cursor()
    now_ts = int(time.time())

    cur.execute("""
      UPDATE jobs SET
        state='processing',
        attempts = attempts + 1,
        updated_at = ? 
      WHERE id = (
        SELECT id FROM jobs
        WHERE state='pending' AND IFNULL(next_run,0) <= ?
        ORDER BY created_at
        LIMIT 1
      )
    """, (datetime.datetime.utcnow().isoformat()+"Z", now_ts))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        return None
    
    cur.execute("SELECT * FROM jobs WHERE state='processing' ORDER BY updated_at DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

# ---------- Update job states ----------
def mark_job_completed(job_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE jobs SET state='completed', updated_at=? WHERE id=?", (datetime.datetime.utcnow().isoformat()+"Z", job_id))
    conn.commit()
    conn.close()

def mark_job_failed_and_schedule(job_id, attempts, max_retries, last_error, backoff_base):
    conn = get_conn()
    cur = conn.cursor()
    now = int(time.time())
    if attempts < max_retries:
        
        delay = int(backoff_base ** attempts)
        next_run = now + delay
        cur.execute("""
          UPDATE jobs SET state='pending', updated_at=?, next_run=?, last_error=?
          WHERE id=?
        """, (datetime.datetime.utcnow().isoformat()+"Z", next_run, last_error, job_id))
    else:
       
        cur.execute("""
          UPDATE jobs SET state='dead', updated_at=?, last_error=?
          WHERE id=?
        """, (datetime.datetime.utcnow().isoformat()+"Z", last_error, job_id))
    conn.commit()
    conn.close()

def retry_dlq_job(job_id):
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
      UPDATE jobs SET state='pending', attempts=0, next_run=0, updated_at=? WHERE id=? AND state='dead'
    """, (datetime.datetime.utcnow().isoformat()+"Z", job_id))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0

# ---------- Worker process ----------
def worker_loop(stop_event: Event):
    """
    Each worker process executes this loop.
    stop_event is an Event that is set for graceful shutdown.
    """
    backoff_base = get_config("backoff_base")
  
    try:
        backoff_base = float(backoff_base)
    except:
        backoff_base = float(DEFAULT_CONFIG["backoff_base"])

    while not stop_event.is_set():
        job = claim_job_atomic()
        if not job:
            
            time.sleep(0.5)
            continue

        job_id = job["id"]
        cmd = job["command"]
        attempts = int(job["attempts"])
        max_retries = int(job["max_retries"])
        click.echo(f"[worker {os.getpid()}] claimed job={job_id} attempts={attempts}/{max_retries} cmd={cmd}")

        try:
            
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            exit_code = proc.returncode
            if exit_code == 0:
                click.echo(f"[worker {os.getpid()}] job {job_id} completed: stdout={proc.stdout.strip()}")
                mark_job_completed(job_id)
            else:
                err = proc.stderr.strip() or proc.stdout.strip() or f"exit_code:{exit_code}"
                click.echo(f"[worker {os.getpid()}] job {job_id} failed (code {exit_code}): {err}")
                mark_job_failed_and_schedule(job_id, attempts, max_retries, err, backoff_base)
        except Exception as e:
            err = str(e)
            click.echo(f"[worker {os.getpid()}] job {job_id} exception: {err}")
            mark_job_failed_and_schedule(job_id, attempts, max_retries, err, backoff_base)

    click.echo(f"[worker {os.getpid()}] graceful shutdown triggered.")


# ---------- Worker management (parent) ----------
class WorkerManager:
    def __init__(self):
        self.procs = []
        self.stop_event = Event()

    def start(self, count):
        if self.procs:
            click.echo("workers already running")
            return
        click.echo(f"starting {count} worker(s)...")
        for _ in range(count):
            p = Process(target=worker_loop, args=(self.stop_event,))
            p.start()
            self.procs.append(p)
        click.echo(f"started {len(self.procs)} worker processes")

    def stop(self):
        if not self.procs:
            click.echo("no workers running")
            return
        click.echo("stopping workers gracefully...")
        
        self.stop_event.set()
        
        for p in self.procs:
            p.join(timeout=10)
            if p.is_alive():
                click.echo(f"worker pid {p.pid} didn't exit, terminating")
                p.terminate()
        self.procs = []
       
        self.stop_event = Event()
        click.echo("workers stopped")


worker_manager = None

# ---------- CLI ----------
@click.group(help="queuectl - lightweight job queue CLI")
def cli():
    print("[queuectl] Initializing database...", file=sys.stderr)
    init_db()
    print(f"[queuectl] Database ready: {DB_PATH}", file=sys.stderr)

# Enqueue
@cli.command(help="enqueue a job JSON: e.g. queuectl enqueue '{\"id\":\"job1\",\"command\":\"sleep 2\"}'")
@click.argument("job_json", type=str)
def enqueue(job_json):
    try:
        job_id = enqueue_job(job_json)
        click.echo(f"enqueued job {job_id}")
    except Exception as e:
        click.echo(f"error enqueueing job: {e}", err=True)
        sys.exit(1)

# Worker commands
@cli.group(help="worker commands")
def worker():
    pass

@worker.command("start", help="start workers: --count N")
@click.option("--count", default=1, show_default=True, help="number of worker processes")
def worker_start(count):
    global worker_manager
    init_db()
    if worker_manager is None:
        worker_manager = WorkerManager()
    worker_manager.start(count)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("parent received interrupt, stopping workers...")
        worker_manager.stop()

@worker.command("stop", help="stop running workers (if this process started them)")
def worker_stop():
    global worker_manager
    if worker_manager is None:
        click.echo("no local worker manager found. If you started workers in another terminal/process, stop them there.")
    else:
        worker_manager.stop()

# status
@cli.command(help="show summary of job states & active workers")
def status():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT state, COUNT(*) as c FROM jobs GROUP BY state")
    rows = cur.fetchall()
    summary = {r["state"]: r["c"] for r in rows}
    conn.close()
    click.echo("job states summary:")
    for s in ["pending", "processing", "completed", "failed", "dead"]:
        click.echo(f"  {s}: {summary.get(s,0)}")
    
    active = worker_manager.procs if 'worker_manager' in globals() and worker_manager else []
    click.echo(f"active local worker processes: {len(active)}")

# list
@cli.command(help="list jobs, optionally filter by state")
@click.option("--state", default=None, help="filter by state")
def list(state):
    rows = list_jobs(state)
    if not rows:
        click.echo("no jobs")
        return
    for r in rows:
        
        click.echo(json.dumps({
            "id": r["id"],
            "command": r["command"],
            "state": r["state"],
            "attempts": r["attempts"],
            "max_retries": r["max_retries"],
            "next_run": r["next_run"],
            "updated_at": r["updated_at"]
        }))

# DLQ
@cli.group(help="dead-letter-queue commands")
def dlq():
    pass

@dlq.command("list", help="list jobs in DLQ (state=dead)")
def dlq_list():
    dead = list_jobs("dead")
    if not dead:
        click.echo("DLQ empty")
        return
    for r in dead:
        click.echo(json.dumps({
            "id": r["id"],
            "command": r["command"],
            "attempts": r["attempts"],
            "max_retries": r["max_retries"],
            "last_error": r["last_error"],
            "updated_at": r["updated_at"]
        }))

@dlq.command("retry", help="retry job from DLQ: dlq retry job_id")
@click.argument("job_id")
def dlq_retry(job_id):
    ok = retry_dlq_job(job_id)
    if ok:
        click.echo(f"job {job_id} moved from dead -> pending")
    else:
        click.echo(f"job {job_id} not in dead state or not found", err=True)
        sys.exit(1)

# config
@cli.group(help="configuration")
def config():
    pass

@config.command("set", help="set config key value: e.g. config set max_retries 5")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    # attempt to parse numeric types
    try:
        parsed = json.loads(value)
    except:
        parsed = value
    set_config(key, parsed)
    click.echo(f"set {key} = {parsed}")

@config.command("get", help="get config key")
@click.argument("key")
def config_get(key):
    v = get_config(key)
    click.echo(json.dumps(v))

# quick tests helper
@cli.command("demo", help="run a small demo: enqueue 3 jobs then start a worker for 6 seconds")
def demo():
    # enqueue a success job, a failing job, and a slow job
    enqueue_job(json.dumps({"id":"demo-ok","command":"echo demo ok","max_retries":2}))
    enqueue_job(json.dumps({"id":"demo-fail","command":"bash -c 'exit 1'","max_retries":2}))
    enqueue_job(json.dumps({"id":"demo-sleep","command":"sleep 2 && echo slept","max_retries":1}))
    # start a worker process in background in this process
    global worker_manager
    if worker_manager is None:
        worker_manager = WorkerManager()
    worker_manager.start(2)
    click.echo("demo: workers running for 8 seconds...")
    try:
        time.sleep(8)
    finally:
        worker_manager.stop()
    click.echo("demo finished. Status:")
    ctx = click.get_current_context()
    ctx.invoke(status)

if __name__ == "__main__":
    cli()

