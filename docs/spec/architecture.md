# Architecture

## High-Level Pipeline

```text
                    ┌──────────────────────────┐
                    │      Frontend / UI       │
                    │  Upload, Timeline, Rank  │
                    │  (placeholder)           │
                    └────────────┬─────────────┘
                                 │ HTTP
                                 ▼
                    ┌──────────────────────────┐
                    │    API / Orchestrator    │
                    │  FastAPI · Port 8000     │
                    │  /health  /ready         │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
   ┌──────────────────┐ ┌────────────────┐ ┌────────────────┐
   │   worker_cpu     │ │     Redis      │ │   PostgreSQL   │
   │   ffmpeg         │ │   Job Queue    │ │   Metadata     │
   │   shot detect    │ │   Port 6379    │ │   Port 5432    │
   └────────┬─────────┘ └────────────────┘ └────────────────┘
            │
            ▼
   ┌──────────────────┐
   │   worker_gpu     │
   │   WhisperX ASR   │
   │   (CUDA)         │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Semantic Segmentation      │
   │   Topic shifts, rhet. cuts   │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Candidate Generator        │
   │   50–150 clip candidates     │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Feature Extraction         │
   │   text / audio / video /     │
   │   channel signals            │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Scoring Engine             │
   │   hook / retention / share   │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Meta Ranker                │
   │   XGBoost / LightGBM         │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Packaging Engine           │
   │   subtitles, titles,         │
   │   overlays, 9:16 export      │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Export + Feedback Store    │
   │   publish metrics,           │
   │   retraining data            │
   └──────────────────────────────┘
```

---

## Services & Containers

| Service | Image | Port | Purpose |
| --- | --- | --- | --- |
| `api` | `Dockerfile.api` | 8000 | FastAPI app + Alembic migrations on startup |
| `worker_cpu` | `Dockerfile.worker_cpu` | — | ffmpeg ingestion, shot detection |
| `worker_gpu` | `Dockerfile.worker_gpu` | — | WhisperX ASR (NVIDIA GPU, 12 GB limit) |
| `postgres` | `postgres:16-alpine` | 5432 | Primary database |
| `redis` | `redis:7-alpine` | 6379 | Job queue |

All services share a `.env` file. `api`, `worker_cpu`, and `worker_gpu` depend on postgres and redis being healthy before starting.

**Shared volume:** `./storage` mounted at `/storage` in all three app containers.

```text
storage/
├── videos/     # uploaded source files
├── clips/      # cut segments
├── exports/    # final 9:16 shorts
└── models/     # ML model cache
```

---

## Data Model

### `videos`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `filename` | String(512) | |
| `original_path` | String(1024) | path under `/storage/videos` |
| `duration_seconds` | Float | nullable |
| `resolution` | String(32) | e.g. `1920x1080` |
| `fps` | Float | nullable |
| `status` | String(64) | default `uploaded` |
| `created_at` | DateTime TZ | |

### `jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | indexed, cascade delete |
| `status` | Enum | see below |
| `error_message` | Text | nullable |
| `created_at` | DateTime TZ | |
| `updated_at` | DateTime TZ | auto-updated |

**Job status flow:**

```text
uploaded → ingesting → ready_for_asr → transcribing → transcribed
                                    ↘
                                      failed
```

### `transcript_segments`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | indexed, cascade delete |
| `job_id` | UUID FK→jobs | indexed, cascade delete |
| `segment_index` | Integer | ordering |
| `start_time` | Float | seconds |
| `end_time` | Float | seconds |
| `text` | Text | transcribed words |
| `words` | JSONB | word-level timing + confidence |
| `created_at` | DateTime TZ | |

---

## AI Components

### Prompts (`ai/prompts/`)

| File | Purpose | Status |
| --- | --- | --- |
| `scoring.md` | Virality assessment — hook/retention/share scores | Done |
| `segmentation.md` | Topic boundary detection | Stub |
| `packaging.md` | Subtitle/title generation | Stub |

### Schemas (`ai/schemas/`)

| File | Fields |
| --- | --- |
| `clip_candidate.json` | `clip_id`, `start`, `end`, `type`, `features` (hook_strength, novelty, clarity) |
| `clip_score.json` | `clip_id`, `hook_score`, `retention_score`, `share_score`, `viral_score`, `reasons` |
| `video_metadata.json` | (stub) |

---

## Implementation Status

| Component | Status |
| --- | --- |
| Docker Compose stack | Done |
| PostgreSQL schema + Alembic | Done (no migrations generated yet) |
| FastAPI skeleton + health checks | Done |
| Pydantic config + env loading | Done |
| CPU worker — ffmpeg ingestion | Stub |
| GPU worker — WhisperX ASR | Stub |
| Redis job queue integration | Stub |
| Service modules (ingestion, asr, storage, jobs) | Stubs |
| Semantic segmentation | Not started |
| Candidate generator | Not started |
| Scoring engine | Not started |
| Meta ranker (XGBoost) | Not started |
| Packaging engine | Not started |
| Frontend | Placeholder |
