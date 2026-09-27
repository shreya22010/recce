"""Video walkthroughs per section.

Search URLs rather than specific video IDs. A hand-picked video is out of date
or deleted within a year and there is no way to notice; a search for the topic
keeps working and shows the student what is current.
"""
from urllib.parse import quote_plus

QUERIES = {
    "aptitude": ["quantitative aptitude for placements full course",
                 "aptitude shortcuts tricks placement"],
    "reasoning": ["logical reasoning for placements full course",
                  "blood relations seating arrangement tricks"],
    "verbal": ["verbal ability for placements", "english communication round placement tips"],
    "cs_mcq": ["operating systems interview questions", "dbms interview questions",
               "computer networks interview questions", "oops interview questions"],
    "output": ["c output questions interview", "java output based questions interview"],
    "sql": ["sql interview questions and answers", "sql joins explained"],
    "coding": ["dsa for placements full course", "coding round preparation"],
    "technical": ["technical interview questions freshers", "project explanation interview"],
    "hr": ["hr interview questions and answers freshers", "tell me about yourself answer"],
    "plan": ["placement preparation strategy 1 month"],
    "overview": [],
}


def for_section(section, company=None):
    out = []
    for q in QUERIES.get(section, []):
        out.append({"title": q,
                    "url": f"https://www.youtube.com/results?search_query={quote_plus(q)}"})
    if company and section in ("overview", "hr", "technical"):
        q = f"{company} interview experience placement"
        out.insert(0, {"title": q,
                       "url": f"https://www.youtube.com/results?search_query={quote_plus(q)}"})
    return out
