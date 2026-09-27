-- Recce: interview intelligence from students who actually sat the drive.
--
-- The whole product rests on one claim: when this says "asked by 12 students",
-- those were twelve independent people. Everything that protects that claim is
-- enforced here rather than in application code, because a trust signal that
-- depends on remembering to check it in every code path is not a trust signal.

create table if not exists student (
  id            integer primary key,
  email_hash    text not null unique,   -- sha256 of the college email, never the address
  batch         integer not null,       -- graduating year
  branch        text,
  verified_at   text,
  created_at    text not null default (datetime('now'))
);

create table if not exists company (
  id        integer primary key,
  name      text not null unique,       -- canonical, matched against jobscout's board names
  slug      text not null unique
);

-- a single visit by a single company to a single campus on a date
create table if not exists drive (
  id          integer primary key,
  company_id  integer not null references company(id),
  campus      text not null,
  held_on     text not null,
  role        text,
  ctc_lpa     real,
  created_at  text not null default (datetime('now')),
  unique (company_id, campus, held_on, role)
);

create table if not exists round (
  id        integer primary key,
  drive_id  integer not null references drive(id),
  seq       integer not null,           -- 1, 2, 3 in the order they happened
  kind      text not null,              -- aptitude | coding | tech | managerial | hr
  unique (drive_id, seq)
);

-- One row per student per drive. The unique constraint is the anti-gaming
-- measure: without it a single enthusiastic person can manufacture consensus
-- and every count on the site becomes meaningless.
create table if not exists submission (
  id            integer primary key,
  student_id    integer not null references student(id),
  drive_id      integer not null references drive(id),
  reached_seq   integer not null,       -- furthest round they got to
  selected      integer not null default 0,
  submitted_at  text not null default (datetime('now')),
  flagged       integer not null default 0,   -- moderation
  unique (student_id, drive_id)
);

-- what one student says they were asked, in their own words
create table if not exists reported_question (
  id             integer primary key,
  submission_id  integer not null references submission(id),
  round_seq      integer not null,
  raw_text       text not null,
  created_at     text not null default (datetime('now'))
);

-- the merged question: many raw reports collapse into one of these
create table if not exists canonical_question (
  id            integer primary key,
  text          text not null,          -- the clearest phrasing seen
  topic         text,                   -- arrays, dp, sql, os, dbms, hr...
  created_at    text not null default (datetime('now'))
);

-- Deliberately stores the score that caused the merge. When precision is
-- reported later, the threshold has to be auditable, and a merge you cannot
-- explain is a merge you cannot defend in an interview.
create table if not exists question_link (
  reported_id   integer primary key references reported_question(id),
  canonical_id  integer not null references canonical_question(id),
  similarity    real not null,
  method        text not null,          -- exact | embedding | manual
  linked_at     text not null default (datetime('now'))
);

-- hand-labelled pairs, the ground truth precision/recall is measured against
create table if not exists dedup_label (
  a_id      integer not null references reported_question(id),
  b_id      integer not null references reported_question(id),
  same      integer not null,           -- 1 = same question, 0 = different
  note      text,
  primary key (a_id, b_id)
);

-- predictions made before a drive, scored against it afterwards
create table if not exists prediction (
  id           integer primary key,
  drive_id     integer not null references drive(id),
  made_at      text not null default (datetime('now')),
  topics       text not null,           -- json array, ranked
  scored_at    text,
  hit_rate     real                     -- share of actual questions the topics covered
);

create index if not exists ix_sub_drive   on submission(drive_id);
create index if not exists ix_rq_sub      on reported_question(submission_id);
create index if not exists ix_link_canon  on question_link(canonical_id);
create index if not exists ix_drive_co    on drive(company_id);

-- Answers are cached so a question costs one model call ever, not one per
-- student. A campus asks a few hundred distinct questions, so this keeps the
-- whole feature inside a free tier indefinitely instead of burning quota the
-- week everyone starts revising.
create table if not exists answer (
  id          integer primary key,
  q_norm      text not null,
  language    text not null default '',
  kind        text not null,
  question    text not null,
  body        text not null,
  model       text,
  created_at  text not null default (datetime('now')),
  unique (q_norm, language)
);

-- A generated prep package, one row per company per section. Generated once and
-- reused, because the material for a company's aptitude round does not change
-- between students and regenerating it per visitor would burn quota for nothing.
create table if not exists package (
  id          integer primary key,
  company     text not null,
  section     text not null,
  content     text not null,          -- json
  model       text,
  created_at  text not null default (datetime('now')),
  unique (company, section)
);

-- Search results are cached permanently. The free search endpoints throttle an
-- IP after a handful of rapid queries, which is exactly what happens when
-- several companies are built in a row, so a result once obtained is never
-- fetched again.
create table if not exists search_cache (
  query       text primary key,
  results     text not null,        -- json
  fetched_at  text not null default (datetime('now'))
);

-- What this person has already done with a posting. Lived in the crawler's
-- migration, which never ran here, so a deployed match() asked for a table that
-- did not exist. They belong with the rest of the schema.
create table if not exists applied (
  url         text primary key,
  applied_at  text not null default (datetime('now')),
  note        text
);

create table if not exists hidden (
  url        text primary key,
  hidden_at  text not null default (datetime('now')),
  reason     text
);

create table if not exists runs (
  id      integer primary key,
  ran_at  text not null default (datetime('now')),
  found   integer,
  added   integer
);
