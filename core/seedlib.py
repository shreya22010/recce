"""Shared question phrasings, grouped by topic, for the synthetic seed."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from topics import topic_of

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
from seed_dev import GROUPS

GROUPS_BY_TOPIC = {}
for g in GROUPS:
    GROUPS_BY_TOPIC.setdefault(topic_of(g[0]), []).append(g)
