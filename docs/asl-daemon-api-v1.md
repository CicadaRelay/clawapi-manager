# ASL Daemon API v1 — Go Service Spec

Wire: Unix Domain Socket + MessagePack
Envelope: `{version: 1, request_id, method, idem_key?, body}`
Error: `{code, message, retryable, details}`

## Three Planes

| Plane | RPC | Hot path? |
|---|---|---|
| Orchestration | submit_job, upsert_tasks, cancel | No |
| Execution | register_agent, heartbeat, pull_tasks, finish_task | Yes |
| Budget | request_action_budget, finish_action | Yes |

---

## Orchestration Plane

### 1. submit_job

```
Request:
  job_id_hint?:    string
  description:     string
  priority:        int32
  decomposition:   "external" | "planner_agent" | "none"
  initial_payload: map
  initial_tasks:   []TaskSpec  // only for external/none

Response:
  job_id:          string
  state:           "pending_planning" | "ready" | "running"
  root_task_ids:   []string
```

### 2. upsert_tasks

```
Request:
  source_task_id?: string     // planner task that spawned these
  tasks:           []TaskSpec

TaskSpec:
  task_id_hint?:   string
  job_id:          string
  kind:            string     // "plan", "code", "review", "test", "decompose"
  priority:        int32
  spec:            map        // task-specific payload
  depends_on:      []string   // task IDs
  requirements:    TaskRequirements
  max_retries:     uint16     // default 3
  idempotency_key?: string

TaskRequirements:
  all_of:          []string   // must have all
  any_of:          []string   // must have one
  avoid:           []string   // soft exclusion
  min_model_tier:  "small" | "medium" | "large"

Response:
  task_ids:        []string
```

### 3. cancel

```
Request:
  scope:           "job" | "task" | "session"
  id:              string
  reason:          string

Response:
  accepted:        bool
  affected:        []string   // cancelled task/action IDs
```

---

## Execution Plane

### 4. register_agent

```
Request:
  agent_id:        string
  capabilities:    AgentCapabilities
  model_tier:      "small" | "medium" | "large"
  max_concurrency: uint16    // how many tasks this agent runs in parallel
  heartbeat_every_ms: uint32 // suggested interval
  client_version:  string
  session_labels:  map

AgentCapabilities:
  roles:           []string  // "plan", "code", "review", "test", "decompose"
  langs:           []string  // "python", "typescript", "go", "rust"
  tools:           []string  // "git", "pytest", "npm", "docker"
  modes:           []string  // "read_only", "write", "long_running"

Response:
  session_id:      string
  lease_ttl_ms:    uint32    // how long before agent considered dead
  heartbeat_every_ms: uint32 // server-confirmed interval
  drain:           bool
  server_epoch:    uint64    // for crash recovery
```

### 5. heartbeat

```
Request:
  session_id:      string
  status:          "idle" | "busy" | "degraded"
  active_tasks:    []ActiveTaskStatus

ActiveTaskStatus:
  lease_id:        string
  task_id:         string
  state:           "running" | "blocked" | "waiting_budget"
  progress?:       uint8     // 0-100

Response:
  acked_at_ms:     uint64
  renewed_leases:  []string  // lease IDs confirmed renewed
  cancel_tasks:    []string  // tasks daemon wants agent to abort
  drain:           bool
  shutdown:        bool
```

### 6. pull_tasks

```
Request:
  session_id:      string
  max_tasks:       uint16    // default 1
  wait_ms:         uint32    // long-poll timeout (0 = no wait)
  accept_roles?:   []string  // optional override of registered roles

Response:
  assignments:     []TaskLease
  retry_after_ms:  uint32    // if no tasks available
  drain:           bool
  shutdown:        bool

TaskLease:
  lease_id:        string
  task_id:         string
  job_id:          string
  kind:            string
  priority:        int32
  spec:            map       // task payload
  requirements:    TaskRequirements
  cost_class:      "cheap" | "normal" | "expensive" | "unknown"
  lease_expires_ms: uint64
  attempt:         uint16    // retry count
```

### 7. finish_task

```
Request:
  session_id:      string
  lease_id:        string
  task_id:         string
  outcome:         "success" | "failed" | "retryable" | "canceled"
  summary:         string
  result:          map       // structured result
  artifacts:       []ArtifactRef
  spawned_task_ids: []string // informational
  error_code?:     string
  retry_delay_ms?: uint32

ArtifactRef:
  kind:            string    // "git_diff", "log", "patch", "json"
  uri:             string    // file:// or git:// or http://
  digest:          string    // sha256
  size:            uint64

Response:
  ack:             bool
```

---

## Budget Plane

### 8. request_action_budget

Atomic: estimate + queue + reserve in one call.
Replaces old enqueue_action + reserve_budget.

```
Request:
  session_id:      string
  task_id:         string
  action_id:       string
  estimate:        CostEstimate
  mode:            "try" | "wait"
  max_wait_ms:     uint32

CostEstimate:
  prompt_tokens_max:     uint32
  completion_tokens_max: uint32
  model_class:           "fast" | "smart" | "premium"
  cost_units:            uint32  // normalized internal budget units

Response:
  status:          "granted" | "queued" | "denied"
  grant?:          BudgetGrant
  queue_pos?:      uint32
  retry_after_ms?: uint32
  reason?:         string

BudgetGrant:
  reservation_id:  string
  granted_units:   uint32
  expires_at_ms:   uint64
```

### 9. finish_action

```
Request:
  reservation_id:  string
  task_id:         string
  action_id:       string
  outcome:         "committed" | "released" | "failed"
  actual?:         ActualCost
  error_code?:     string

ActualCost:
  prompt_tokens:      uint32
  completion_tokens:  uint32
  cost_units:         uint32
  model:              string
  latency_ms:         uint32

Response:
  ack:             bool
```

---

## Admin (optional, not on hot path)

### 10. get_snapshot

```
Request:
  scope:           "overview" | "agents" | "jobs" | "budget"

Response:
  (scope-dependent snapshot data)
```

---

## State Machines

### Job: pending_planning → ready → running → done | failed | canceled
### Task: pending → ready → leased → running → done | failed | retryable | canceled
### Action: requested → granted → committed | released | failed

### Task Lifecycle

```
pending ──(all deps done)──▶ ready
ready ──(agent pulls)──▶ leased
leased ──(agent starts)──▶ running
running ──(finish_task success)──▶ done ──▶ unblock dependents
running ──(finish_task retryable)──▶ ready (retry_count++)
running ──(finish_task failed)──▶ failed
running ──(lease expires, no heartbeat)──▶ ready (auto-reschedule)
any ──(cancel)──▶ canceled
```

---

## Design Rules

1. Daemon has NO intelligence — never calls LLM directly
2. Large payloads use ArtifactRef, not inline
3. All RPC are idempotent when idem_key is set
4. Budget reservation expires if finish_action not called within grant TTL
5. Task lease expires if heartbeat stops — task auto-reschedules
6. Capability matching: hard filter (AllOf/AnyOf) then daemon-internal scoring
7. Wire encoding: MessagePack with JSON Schema for type definitions
