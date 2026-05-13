# PyPI typo-squatting check

Status: Deferred
Deferred because: Dropped by decision. The ultranormalization reverse-lookup covers the most common rejection class. Typo-squatting against the top 200 packages is a niche check.
Trigger: Revisit if users report typo-squatting rejections that rlsbl check didn't catch.

## What it would do

Port PyPI's 5 typo-squatting pattern checks from warehouse/packaging/typosnyper.py:
1. Repeated characters (reequests -> requests)
2. Omitted characters (insert at each position)
3. Swapped characters (transpose adjacent pairs)
4. Swapped words (permute hyphen-separated tokens)
5. Common typos (QWERTY adjacency substitution)

Checked against the top 200 most-depended-upon PyPI packages. Pure local computation, no API calls.
