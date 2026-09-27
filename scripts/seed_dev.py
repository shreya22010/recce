"""A synthetic development set for tuning the deduplicator.

IMPORTANT: this data is invented. It exists so the matching pipeline can be
built and tuned before a single real student has submitted anything, and so
the threshold is chosen against something rather than guessed. Every number
produced from it is a development number and must be labelled as such.

The real precision and recall figures come from labelling real submissions,
and until those exist there is nothing to report publicly.

Each GROUP is one underlying question, written the way different students
actually write it: shorthand, partial recall, and the interviewer's framing
mixed in with the student's own words.
"""

GROUPS = [
 ["Reverse a LL", "reverse a singly linked list", "Given head, reverse the list in place",
  "he asked me to reverse linked list iteratively", "reverse a linked list without recursion"],
 ["detect loop in linked list", "cycle detection in a LL", "find if linked list has a cycle",
  "Floyd cycle detection algorithm"],
 ["find middle of linked list", "middle element of a LL in one pass",
  "get the middle node of linked list"],
 ["0/1 knapsack using dynamic programming", "solve knapsack problem DP",
  "asked me DP knapsack", "knapsack 0 1 problem"],
 ["longest common subsequence", "LCS of two strings", "find lcs using dp"],
 ["longest increasing subsequence", "LIS problem", "find the longest increasing subseq"],
 ["find duplicate in array", "detect duplicate element in an array",
  "given array find repeating element"],
 ["two sum problem", "find two numbers that add to target", "pair with given sum in array"],
 ["sort an array of 0s 1s and 2s", "dutch national flag problem", "sort 012 array"],
 ["maximum subarray sum", "kadane algorithm", "largest sum contiguous subarray"],
 ["check if string is palindrome", "palindrome check for a string",
  "is the given string a palindrome"],
 ["reverse words in a sentence", "reverse the order of words in a string"],
 ["find first non repeating character", "first unique character in a string"],
 ["check anagram of two strings", "are these two strings anagrams"],
 ["level order traversal of binary tree", "BFS traversal of a tree", "print tree level by level"],
 ["height of a binary tree", "find depth of binary tree", "maximum depth of a tree"],
 ["lowest common ancestor in BST", "LCA of two nodes in binary search tree"],
 ["validate a BST", "check if given tree is a binary search tree"],
 ["implement LRU cache", "design least recently used cache", "LRU cache design question"],
 ["difference between stack and queue", "stack vs queue difference"],
 ["implement stack using queue", "make a stack with two queues"],
 ["what is deadlock", "explain deadlock in OS", "deadlock conditions in operating system",
  "four necessary conditions for deadlock"],
 ["difference between process and thread", "process vs thread in operating system"],
 ["what is paging in OS", "explain paging and segmentation"],
 ["difference between DELETE and TRUNCATE", "delete vs truncate in SQL"],
 ["what are joins in SQL", "explain different types of joins",
  "inner join vs outer join difference"],
 ["normalization in DBMS", "explain 1NF 2NF 3NF", "what is database normalization"],
 ["what is indexing in database", "how does indexing work in dbms", "explain db index"],
 ["ACID properties", "explain ACID in dbms", "what does acid stand for in databases"],
 ["four pillars of OOPS", "explain oops concepts", "what are the principles of object oriented programming"],
 ["difference between abstraction and encapsulation", "abstraction vs encapsulation"],
 ["method overloading vs overriding", "difference between overloading and overriding"],
 ["what is polymorphism", "explain polymorphism with example"],
 ["TCP vs UDP", "difference between tcp and udp protocol"],
 ["what happens when you type a URL in browser", "explain what happens when you enter google.com"],
 ["explain OSI model layers", "what are the 7 layers of OSI"],
 ["tell me about yourself", "introduce yourself", "give a brief intro about yourself"],
 ["why should we hire you", "why do you think you are fit for this role"],
 ["where do you see yourself in 5 years", "what are your five year goals"],
 ["tell me about your project", "explain your final year project",
  "walk me through a project on your resume"],
 ["what are your strengths and weaknesses", "tell me your strength and weakness"],
 ["are you willing to relocate", "do you have any location preference"],
 ["time complexity of quicksort", "what is worst case complexity of quick sort"],
 ["difference between array and linked list", "array vs linked list"],
 ["binary search implementation", "implement binary search on sorted array",
  "write code for binary search"],
]

if __name__ == "__main__":
    import os, sqlite3
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = sqlite3.connect(os.path.join(here, "recce.db"))
    db.executescript(open(os.path.join(here, "core", "schema.sql")).read())

    db.execute("delete from reported_question where submission_id = -1")
    rows = []
    for gi, group in enumerate(GROUPS):
        for text in group:
            cur = db.execute(
                "insert into reported_question (submission_id, round_seq, raw_text)"
                " values (-1, 0, ?)", (text,))
            rows.append((cur.lastrowid, gi))
    db.commit()

    import json
    json.dump({str(qid): gi for qid, gi in rows},
              open(os.path.join(here, "dev_truth.json"), "w"), indent=0)
    print(f"{len(GROUPS)} questions, {len(rows)} phrasings  (synthetic dev set)")
