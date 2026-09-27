"""
The skill taxonomy, mined from the corpus rather than invented.

Hand-writing a list of technologies guarantees two failures: it contains what
the author happens to know, and it silently omits whatever is currently being
hired for. Both are invisible until someone notices their matches are strange.

So the vocabulary is seeded with patterns that identify a technology by shape,
then confirmed against the indexed descriptions. A term earns its place by
appearing in real job requirements, and its weight comes from how rare it is:
a skill named in 40 of 10,000 jobs says far more about a role than one named in
4,000.
"""
import math, re, sqlite3
from collections import Counter

# Seeds. Not the final list — the corpus decides what survives and what it is
# worth. These exist because a technology name is not identifiable by shape
# alone; "go" and "rust" are ordinary words until you know to look for them.
SEED = """
python, java, javascript, typescript, golang, kotlin, swift, scala, ruby, rust, php,
c++, c#, .net, dart, elixir, haskell, clojure, matlab, bash, powershell, sql, plsql,
react, angular, vue, svelte, next.js, nuxt, remix, jquery, redux, tailwind, bootstrap,
node.js, express, nestjs, django, flask, fastapi, rails, spring boot, laravel,
graphql, rest api, grpc, websocket, protobuf, openapi, swagger,
postgres, postgresql, mysql, mongodb, redis, cassandra, dynamodb, elasticsearch,
sqlite, oracle, snowflake, bigquery, redshift, clickhouse, neo4j, pgvector, pinecone,
weaviate, milvus, qdrant,
aws, azure, gcp, kubernetes, docker, terraform, ansible, jenkins, circleci,
github actions, gitlab ci, argocd, helm, prometheus, grafana, datadog, splunk,
cloudflare, vercel, netlify, cloudformation, pulumi,
kafka, rabbitmq, airflow, spark, hadoop, flink, dbt, databricks,
pandas, numpy, scipy, scikit-learn, pytorch, tensorflow, keras, xgboost,
lightgbm, huggingface, langchain, llamaindex, opencv, nltk, spacy,
mlflow, kubeflow, sagemaker,
llm, rag, embeddings, fine-tuning, prompt engineering, nlp, computer vision,
reinforcement learning, deep learning, machine learning, generative ai,
git, github, gitlab, jira, linux, agile, scrum, ci/cd, tdd, microservices,
oauth, jwt, saml, oidc, encryption, owasp, penetration testing, siem,
figma, firebase, supabase, stripe, twilio, segment, amplitude, posthog
"""

def seed_terms():
    return {t.strip() for t in SEED.replace("\n", " ").split(",") if t.strip()}

def pattern(term):
    """Word-boundary matching that survives the punctuation in real tech names.
    A naive \\b breaks on 'c++', '.net' and 'ci/cd' — the boundary sits in the
    wrong place — so the edges are asserted explicitly."""
    return re.compile(r"(?<![A-Za-z0-9+#.])" + re.escape(term) + r"(?![A-Za-z0-9+#])", re.I)

def build(db_path="jobs.db", min_jobs=8, max_share=0.35):
    """Keep the seeds the corpus actually uses, and weight them by rarity."""
    db = sqlite3.connect(db_path)
    docs = [f"{t} {d or ''}" for t, d in
            db.execute("select title, description from jobs where length(description) > 200")]
    n = len(docs)

    counts = Counter()
    pats = {t: pattern(t) for t in seed_terms()}
    for doc in docs:
        low = doc.lower()
        for t, p in pats.items():
            # cheap containment check first; the regex is the expensive part and
            # most terms are absent from most documents
            if t in low and p.search(doc):
                counts[t] += 1

    tax = {}
    for t, c in counts.items():
        if c < min_jobs:            # too rare to be a real requirement, or a typo
            continue
        if c / n > max_share:       # in a third of all jobs: describes the
            continue                # industry, not what this role needs
        # inverse document frequency: a term in 40 of 10,000 jobs is a far
        # stronger signal about a role than one in 4,000
        tax[t] = round(math.log(n / c), 3)
    return tax, n

if __name__ == "__main__":
    import json
    tax, n = build()
    json.dump(tax, open("taxonomy.json", "w"), indent=1, sort_keys=True)
    print(f"  {len(tax)} skills kept from {n} described jobs\n")
    top = sorted(tax.items(), key=lambda x: -x[1])
    print("  rarest (most informative):")
    for t, w in top[:10]: print(f"    {t:<24} {w}")
    print("\n  most common (least informative):")
    for t, w in top[-8:]: print(f"    {t:<24} {w}")
