"""Assigning a question to a preparation topic.

Topics are the unit the prep set is chosen over, because a student cannot
study "reverse a linked list" as a discrete task but can study linked lists.
Keyword rules rather than a model: the label set is small and fixed, the rules
are auditable, and a wrong label can be fixed in one line instead of retrained.
"""
import re

RULES = [
    ("linked list",   r"linked list|\bll\b|cycle detection|floyd"),
    ("arrays",        r"\barray|subarray|kadane|two sum|duplicate|dutch national|sort 012"),
    ("strings",       r"\bstring|palindrome|anagram|substring|character"),
    ("dynamic prog",  r"dynamic programming|knapsack|\blcs\b|\blis\b|longest common|longest increasing|memo"),
    ("trees",         r"\btree|\bbst\b|traversal|ancestor|\bbfs\b|\bdfs\b|binary search tree"),
    ("stacks queues", r"\bstack|\bqueue|\blru\b|cache"),
    ("searching",     r"binary search|linear search"),
    ("sorting",       r"quicksort|quick sort|merge sort|bubble sort|sorting|time complexity of.*sort"),
    ("operating sys", r"deadlock|paging|segmentation|process|thread|semaphore|scheduling|operating system"),
    ("dbms",          r"\bsql\b|join|normali|\bacid\b|index|truncate|database|dbms|query"),
    ("oops",          r"oops|object oriented|polymorph|inherit|abstraction|encapsulation|overload|overrid"),
    ("networking",    r"\btcp\b|\budp\b|\bosi\b|protocol|http|dns|url in browser|network"),
    ("hr",            r"yourself|hire you|five year|5 years|strength|weakness|relocate|why do you|"
                      r"tell me about your project|final year project|walk me through"),
]
COMPILED = [(t, re.compile(p, re.I)) for t, p in RULES]


def topic_of(text):
    for name, pat in COMPILED:
        if pat.search(text or ""):
            return name
    return "other"


# A question is answerable only when every topic it draws on is known. LRU cache
# needs hash maps and linked lists together; knowing one leaves you stuck. This
# is what makes choosing a study set a real optimisation rather than sorting
# topics by popularity: a topic can be worth little alone and a lot in company.
EXTRA = [
    ("hashing",      r"\blru\b|cache|duplicate|two sum|anagram|first non repeating|first unique|frequency"),
    ("recursion",    r"recursion|recursive|traversal|\bdfs\b|reverse.*linked list|tree|backtrack"),
    ("pointers",     r"linked list|\bll\b|middle|cycle|reverse.*list|two pointer"),
    ("complexity",   r"complexity|big o|time complexity|space complexity|efficient|optimi"),
    ("sorting",      r"sort|order|arrange"),
    ("system design", r"design|\blru\b|cache|scalab"),
]
EXTRA_C = [(t, re.compile(p, re.I)) for t, p in EXTRA]


def topics_of(text):
    """Every topic a question draws on, not just its headline one."""
    out = {topic_of(text)}
    for name, pat in EXTRA_C:
        if pat.search(text or ""):
            out.add(name)
    out.discard("other")
    return out or {"other"}
