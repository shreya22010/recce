"""Where to practise, and where to check that we are not making things up.

Two rules here. Every claim this site makes about what a company asks has to be
traceable to something a student can open and read: either a submission from a
named campus, or a link out to the site it came from. And nothing is copied
from those sites — they are linked, not scraped, because their terms forbid
republishing and because a link is what lets someone cross-check anyway.

Search URLs rather than guessed article paths: a search page for a company is
always valid, where a hand-written slug quietly 404s the moment a site
reorganises.
"""
from urllib.parse import quote_plus

# Practice grounds per round type. These are stable section URLs.
PRACTICE = {
    "coding": [
        ("LeetCode problem set", "https://leetcode.com/problemset/"),
        ("GeeksforGeeks DSA practice", "https://www.geeksforgeeks.org/explore"),
        ("InterviewBit programming", "https://www.interviewbit.com/practice/"),
    ],
    "aptitude": [
        ("IndiaBix aptitude", "https://www.indiabix.com/aptitude/questions-and-answers/"),
        ("GeeksforGeeks aptitude", "https://www.geeksforgeeks.org/aptitude/aptitude-questions-and-answers/"),
        ("PrepInsta aptitude", "https://prepinsta.com/quantitative-aptitude/"),
    ],
    "english": [
        ("IndiaBix verbal ability", "https://www.indiabix.com/verbal-ability/questions-and-answers/"),
        ("IndiaBix verbal reasoning", "https://www.indiabix.com/verbal-reasoning/questions-and-answers/"),
    ],
    "tech": [
        ("GeeksforGeeks DBMS", "https://www.geeksforgeeks.org/dbms/"),
        ("GeeksforGeeks operating systems", "https://www.geeksforgeeks.org/operating-systems/"),
        ("GeeksforGeeks OOPs", "https://www.geeksforgeeks.org/object-oriented-programming-oops-concept-in-java/"),
        ("GeeksforGeeks computer networks", "https://www.geeksforgeeks.org/computer-network-tutorials/"),
    ],
    "hr": [
        ("IndiaBix HR interview", "https://www.indiabix.com/hr-interview/questions-and-answers/"),
        ("GeeksforGeeks HR interview", "https://www.geeksforgeeks.org/hr-interview-questions/"),
    ],
    "managerial": [
        ("IndiaBix HR interview", "https://www.indiabix.com/hr-interview/questions-and-answers/"),
    ],
}

# Per-topic practice, so a question about linked lists links somewhere useful
TOPIC_PRACTICE = {
    "linked list": "https://www.geeksforgeeks.org/data-structures/linked-list/",
    "arrays": "https://www.geeksforgeeks.org/array-data-structure/",
    "strings": "https://www.geeksforgeeks.org/string-data-structure/",
    "trees": "https://www.geeksforgeeks.org/binary-tree-data-structure/",
    "dynamic prog": "https://www.geeksforgeeks.org/dynamic-programming/",
    "stacks queues": "https://www.geeksforgeeks.org/stack-data-structure/",
    "hashing": "https://www.geeksforgeeks.org/hashing-data-structure/",
    "sorting": "https://www.geeksforgeeks.org/sorting-algorithms/",
    "searching": "https://www.geeksforgeeks.org/searching-algorithms/",
    "recursion": "https://www.geeksforgeeks.org/recursion/",
    "dbms": "https://www.geeksforgeeks.org/dbms/",
    "operating sys": "https://www.geeksforgeeks.org/operating-systems/",
    "oops": "https://www.geeksforgeeks.org/object-oriented-programming-oops-concept-in-java/",
    "networking": "https://www.geeksforgeeks.org/computer-network-tutorials/",
    "system design": "https://www.geeksforgeeks.org/system-design-tutorial/",
    "complexity": "https://www.geeksforgeeks.org/analysis-of-algorithms-set-1-asymptotic-analysis/",
    "pointers": "https://www.geeksforgeeks.org/pointers-in-c-and-c-set-1-introduction-arithmetic-and-array/",
    "hr": "https://www.indiabix.com/hr-interview/questions-and-answers/",
}


def cross_check(company):
    """Places to read other people's accounts of this company's process.

    Offered so a student can verify what this site says rather than trust it,
    which matters more here than anywhere else: the whole complaint about
    existing question lists is that nobody can tell where they came from.
    """
    q = quote_plus(company)
    return [
        {"site": "GeeksforGeeks interview experiences",
         "url": f"https://www.geeksforgeeks.org/?s={q}+interview+experience"},
        {"site": "LeetCode Discuss",
         "url": f"https://leetcode.com/discuss/search?query={q}"},
        {"site": "PrepInsta",
         "url": f"https://prepinsta.com/?s={q}"},
        {"site": "AmbitionBox interviews",
         "url": f"https://www.ambitionbox.com/interviews?title={q}"},
        {"site": "Glassdoor interviews",
         "url": f"https://www.glassdoor.co.in/Interview/index.htm?keyword={q}"},
    ]


def reviews_for(company):
    """Where the pay and culture claims can be checked. These sites are the
    ones candidates actually read, and linking beats paraphrasing them."""
    q = quote_plus(company)
    return [
        {"site": "AmbitionBox reviews", "url": f"https://www.ambitionbox.com/reviews?title={q}"},
        {"site": "AmbitionBox salaries", "url": f"https://www.ambitionbox.com/salaries?title={q}"},
        {"site": "Glassdoor reviews",
         "url": f"https://www.glassdoor.co.in/Reviews/index.htm?keyword={q}"},
        {"site": "Levels.fyi", "url": f"https://www.levels.fyi/?search={q}"},
    ]


def practice_for(round_kind):
    return PRACTICE.get(round_kind, [])


def practice_for_topic(topic):
    return TOPIC_PRACTICE.get(topic)
