#!/usr/bin/env python3
import re

query = 'make a task to setup monitoring and give it to admin@domain.com'

patterns = [
    r'task[:\s]+([^,\.;]+?)(?:\s+to\s+[^\s,\.;]*@|$)',  # "task: X to email" or "task: X"
    r'(configure|setup|update|create|build|deploy|review)\s+([^,\.;]+?)(?:\s+(?:to|and\s+assign\s+to)\s+[^\s,\.;]*@|$)',  # "configure X to email" or "configure X"
    r'delegate\s+task:\s*([^,\.;]+?)\s+to\s+',  # "delegate task: X to email"
    r'make\s+a\s+task\s+to\s+([^,\.;]+?)(?:\s+and\s+give\s+it\s+to\s+[^\s,\.;]*@|$)',  # "make a task to X and give it to email"
]

print(f"Query: {query}")
print("=" * 50)

for i, pattern in enumerate(patterns):
    print(f"Pattern {i+1}: {pattern}")
    matches = list(re.finditer(pattern, query, re.IGNORECASE))
    if matches:
        for match in matches:
            print(f"  Match: {match.groups()}")
    else:
        print("  No match")
    print()