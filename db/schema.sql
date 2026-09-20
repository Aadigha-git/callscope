-- CallScope reference schema (PostgreSQL 16). Source of truth = Alembic migrations; this is the snapshot.
CREATE SCHEMA IF NOT EXISTS cs;
CREATE SCHEMA IF NOT EXISTS biz;

-- ---------- enums ----------
CREATE TYPE cs.component_kind   AS ENUM ('asr','tts','llm','vad','turn_detector','judge');
CREATE TYPE cs.model_status     AS ENUM ('candidate','validated','production','retired','rejected');
CREATE TYPE cs.call_channel     AS ENUM ('browser','sip','sim','replay');
CREATE TYPE cs.speaker          AS ENUM ('caller','agent');
CREATE TYPE cs.dataset_kind     AS ENUM ('synthetic','recorded','labelled_failures','mixed');
CREATE TYPE cs.split_name       AS ENUM ('train','dev','test');
CREATE TYPE cs.run_mode         AS ENUM ('stage_replay','text_replay','caller_sim','baseline');
CREATE TYPE cs.run_status       AS ENUM ('queued','running','succeeded','failed','gated_fail');

-- ---------- model inventory / stacks ----------
CREATE TABLE cs.model_versions (
  model_version_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  component         cs.component_kind NOT NULL,
  name              text NOT NULL,
  base_model        text,
  revision          text NOT NULL,
  license           text,
  artifact_uri      text,
  config            jsonb NOT NULL DEFAULT '{}',
  config_sha256     text,
  training_data     jsonb,                       -- dataset ids / notes used for adaptation
  intended_use      text,
  out_of_scope_use  text,
  owner             text NOT NULL,
  status            cs.model_status NOT NULL DEFAULT 'candidate',
  mlflow_run_id     text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (component, name, revision)
);

CREATE TABLE cs.stack_versions (
  stack_version_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label             text NOT NULL UNIQUE,        -- e.g. stack-2026.09.18-a
  asr_mv            uuid NOT NULL REFERENCES cs.model_versions,
  tts_mv            uuid NOT NULL REFERENCES cs.model_versions,
  llm_mv            uuid NOT NULL REFERENCES cs.model_versions,
  vad_mv            uuid REFERENCES cs.model_versions,
  turn_mv           uuid REFERENCES cs.model_versions,
  hermes_version    text NOT NULL,
  plugin_version    text NOT NULL,
  prompt_sha256     text NOT NULL,
  worker_config     jsonb NOT NULL,
  git_sha           text NOT NULL,
  is_production     boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX one_production_stack ON cs.stack_versions ((is_production)) WHERE is_production;

-- ---------- calls ----------
CREATE TABLE cs.calls (
  call_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at        timestamptz NOT NULL,
  ended_at          timestamptz,
  channel           cs.call_channel NOT NULL,
  stack_version_id  uuid NOT NULL REFERENCES cs.stack_versions,
  scenario_id       text,                        -- set for sim/replay
  is_synthetic      boolean NOT NULL DEFAULT false,
  consent_recording boolean NOT NULL,
  consent_donate    boolean NOT NULL DEFAULT false,
  consent_policy_v  text NOT NULL,
  recording_uri     text,
  raw_purged_at     timestamptz,
  end_reason        text,
  flagged           boolean NOT NULL DEFAULT false,
  flag_reasons      text[] NOT NULL DEFAULT '{}',
  CHECK (consent_recording OR channel IN ('sim','replay'))
);
CREATE INDEX calls_started_idx ON cs.calls (started_at DESC);
CREATE INDEX calls_flagged_idx ON cs.calls (flagged) WHERE flagged;

CREATE TABLE cs.turns (
  turn_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id           uuid NOT NULL REFERENCES cs.calls ON DELETE CASCADE,
  idx               int  NOT NULL,
  speaker           cs.speaker NOT NULL,
  t_start_ms        bigint NOT NULL,
  t_end_ms          bigint,
  text              text,
  asr_avg_conf      real,
  interrupted       boolean NOT NULL DEFAULT false,
  spoken_prefix     text,
  UNIQUE (call_id, idx)
);

CREATE TABLE cs.events (
  event_id          uuid PRIMARY KEY,            -- client-generated; dedupe key
  call_id           uuid NOT NULL REFERENCES cs.calls ON DELETE CASCADE,
  turn_id           uuid REFERENCES cs.turns ON DELETE SET NULL,
  t_ms              bigint NOT NULL,
  ts                timestamptz NOT NULL,
  source            text NOT NULL,
  type              text NOT NULL,
  payload           jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX events_call_t_idx ON cs.events (call_id, t_ms);
CREATE INDEX events_type_idx   ON cs.events (type);

CREATE TABLE cs.tool_calls (
  tool_call_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id           uuid NOT NULL REFERENCES cs.calls ON DELETE CASCADE,
  turn_id           uuid REFERENCES cs.turns ON DELETE SET NULL,
  name              text NOT NULL,
  args              jsonb NOT NULL,
  args_scrubbed     jsonb NOT NULL,
  result            jsonb,
  status            text NOT NULL,               -- ok | error | denied
  policy_rule       text,
  mutating          boolean NOT NULL,
  confirmed         boolean,
  started_at        timestamptz NOT NULL,
  latency_ms        int
);
CREATE INDEX tool_calls_call_idx ON cs.tool_calls (call_id);

-- ---------- datasets ----------
CREATE TABLE cs.datasets (
  dataset_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name              text NOT NULL,
  version           text NOT NULL,
  kind              cs.dataset_kind NOT NULL,
  manifest_uri      text NOT NULL,
  manifest_sha256   text NOT NULL,
  n_items           int NOT NULL,
  parent_dataset_id uuid REFERENCES cs.datasets,
  dq_report         jsonb NOT NULL,
  dq_passed         boolean NOT NULL,
  frozen            boolean NOT NULL DEFAULT false,   -- true for frozen test sets
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);

CREATE TABLE cs.dataset_items (
  item_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id        uuid NOT NULL REFERENCES cs.datasets ON DELETE CASCADE,
  split             cs.split_name NOT NULL,
  scenario_id       text NOT NULL,
  variant           text,
  turn_idx          int,
  audio_uri         text NOT NULL,
  audio_sha256      text NOT NULL,
  condition_code    text NOT NULL,               -- C0..C5
  voice_profile     text,
  augmentation      jsonb NOT NULL DEFAULT '{}',
  ref_transcript    text,
  ref_intent        text,
  ref_slots         jsonb,
  ref_expected      jsonb,                       -- expected tool calls / final state
  source_call_id    uuid REFERENCES cs.calls
);
CREATE INDEX dataset_items_ds_split_idx ON cs.dataset_items (dataset_id, split);

-- ---------- evaluation ----------
CREATE TABLE cs.eval_runs (
  run_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id        uuid NOT NULL REFERENCES cs.datasets,
  stack_version_id  uuid NOT NULL REFERENCES cs.stack_versions,
  mode              cs.run_mode NOT NULL,
  git_sha           text NOT NULL,
  thresholds_sha256 text,
  config            jsonb NOT NULL DEFAULT '{}',
  status            cs.run_status NOT NULL DEFAULT 'queued',
  mlflow_run_id     text,
  started_at        timestamptz,
  finished_at       timestamptz
);

CREATE TABLE cs.eval_metrics (
  run_id            uuid NOT NULL REFERENCES cs.eval_runs ON DELETE CASCADE,
  metric            text NOT NULL,               -- e.g. wer, phone_seq_acc, task_success, latency_p95
  slice             text NOT NULL DEFAULT 'all', -- e.g. cond=C1, entity=PHONE, voice=v3
  value             double precision NOT NULL,
  ci_low            double precision,
  ci_high           double precision,
  n                 int NOT NULL,
  PRIMARY KEY (run_id, metric, slice)
);

CREATE TABLE cs.eval_item_results (
  run_id            uuid NOT NULL REFERENCES cs.eval_runs ON DELETE CASCADE,
  item_id           uuid NOT NULL REFERENCES cs.dataset_items,
  hyp_transcript    text,
  wer               real,
  slots_pred        jsonb,
  tool_calls_pred   jsonb,
  latencies_ms      jsonb,
  flags             text[] NOT NULL DEFAULT '{}',
  auto_root_cause   text,
  PRIMARY KEY (run_id, item_id)
);

-- ---------- review workflow ----------
CREATE TABLE cs.root_cause_codes (
  code              text PRIMARY KEY,
  category          text NOT NULL,
  description       text NOT NULL
);

CREATE TABLE cs.review_labels (
  label_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id           uuid NOT NULL REFERENCES cs.calls ON DELETE CASCADE,
  turn_id           uuid REFERENCES cs.turns ON DELETE SET NULL,
  reviewer          text NOT NULL,
  root_cause_code   text NOT NULL REFERENCES cs.root_cause_codes,
  severity          smallint NOT NULL CHECK (severity BETWEEN 1 AND 4),
  notes             text,
  add_to_dataset    text CHECK (add_to_dataset IN ('train','dev')),
  exported_dataset  uuid REFERENCES cs.datasets,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX review_labels_code_idx ON cs.review_labels (root_cause_code);

-- ---------- governance ----------
CREATE TABLE cs.validation_reports (
  report_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id  uuid NOT NULL REFERENCES cs.model_versions,
  eval_run_id       uuid NOT NULL REFERENCES cs.eval_runs,
  thresholds        jsonb NOT NULL,
  results           jsonb NOT NULL,
  passed            boolean NOT NULL,
  report_uri        text,
  signed_off_by     text,
  signed_off_at     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cs.risk_register (
  risk_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id  uuid REFERENCES cs.model_versions,
  category          text NOT NULL,               -- accuracy|fairness|hallucination|privacy|security|availability|cost
  description       text NOT NULL,
  likelihood        smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  impact            smallint NOT NULL CHECK (impact BETWEEN 1 AND 5),
  mitigation        text,
  status            text NOT NULL DEFAULT 'open',
  owner             text NOT NULL,
  reviewed_at       timestamptz
);

-- ---------- fictional business data ----------
CREATE TABLE biz.services (
  service_type      text PRIMARY KEY,
  display_name      text NOT NULL,
  price_range_usd   int4range,
  duration_min      int NOT NULL
);

CREATE TABLE biz.slots (
  slot_id           text PRIMARY KEY,
  service_type      text NOT NULL REFERENCES biz.services,
  starts_at         timestamptz NOT NULL,
  ends_at           timestamptz NOT NULL,
  zip_scope         text[] NOT NULL,
  is_open           boolean NOT NULL DEFAULT true
);
CREATE INDEX slots_open_idx ON biz.slots (service_type, starts_at) WHERE is_open;

CREATE TABLE biz.appointments (
  confirmation_code text PRIMARY KEY,
  customer_name     text NOT NULL,
  phone             text NOT NULL,
  address           text NOT NULL,
  service_type      text NOT NULL REFERENCES biz.services,
  slot_id           text NOT NULL REFERENCES biz.slots,
  notes             text,
  status            text NOT NULL DEFAULT 'booked',   -- booked|rescheduled|cancelled
  idempotency_key   text UNIQUE,
  created_call_id   uuid,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE biz.callbacks (
  ticket_id         text PRIMARY KEY,
  customer_name     text NOT NULL,
  phone             text NOT NULL,
  reason            text NOT NULL,
  preferred_window  text,
  created_call_id   uuid,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE biz.kb_documents (
  doc_id            text PRIMARY KEY,
  title             text NOT NULL,
  body              text NOT NULL,
  tsv               tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED
);
CREATE INDEX kb_tsv_idx ON biz.kb_documents USING gin (tsv);

-- ---------- seed: root-cause taxonomy ----------
INSERT INTO cs.root_cause_codes (code, category, description) VALUES
 ('RC-ASR-ENT','ASR','Entity mis-transcribed (digits, names, addresses)'),
 ('RC-ASR-NOISE','ASR','Errors attributable to noise or channel degradation'),
 ('RC-ASR-HALLU','ASR','Phantom text produced from silence or noise'),
 ('RC-ASR-DROP','ASR','Words dropped or truncated'),
 ('RC-TURN-EARLY','Turn-taking','Endpoint fired while caller still speaking'),
 ('RC-TURN-LATE','Turn-taking','Slow endpoint or dead air'),
 ('RC-TURN-BARGE-MISS','Turn-taking','Caller interrupted but agent kept speaking'),
 ('RC-TURN-BARGE-FALSE','Turn-taking','Agent stopped without a real interruption (echo/noise)'),
 ('RC-LLM-INTENT','LLM/NLU','Wrong intent or routing'),
 ('RC-LLM-SLOT','LLM/NLU','Slot extraction or normalisation error'),
 ('RC-LLM-HALLU','LLM/NLU','Claim not supported by KB or tool results'),
 ('RC-LLM-POLICY','LLM/NLU','Policy violation (skipped confirmation, out of scope)'),
 ('RC-LLM-REPAIR','LLM/NLU','Failed to handle a correction'),
 ('RC-TOOL-ARGS','Tool','Invalid or wrong tool arguments'),
 ('RC-TOOL-ERR','Tool','Tool or backend error'),
 ('RC-TTS-PRON','TTS','Mispronunciation (digits, addresses, names)'),
 ('RC-TTS-ARTIFACT','TTS','Audible artifacts or truncation'),
 ('RC-TTS-LAT','TTS','Slow synthesis'),
 ('RC-SYS-LAT','System','Infrastructure or queueing latency'),
 ('RC-SYS-NET','System','Packet loss or jitter'),
 ('RC-SYS-OTHER','System','Other system fault');
