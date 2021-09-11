#!/usr/bin/env python3

# Check the consistency of Digikam's Tags table
# prints nothing if consistent
# prints inconsistent tags if found

import sys
import argparse
from digikam import Digikam

parser = argparse.ArgumentParser(description="Check Digikam Tags Tree")
parser.add_argument(
    "-q", "--quiet", action="store_true", help="quiet, don't output if tree ok"
)

args = parser.parse_args()

digikam = Digikam()
db = digikam.db()
db2 = digikam.db()

sql = "SELECT id, pid, name FROM Tags WHERE id <> 0"
cur = db.execute(sql)
tags = cur.fetchall()

sqlAncestor = """
WITH RECURSIVE ancestors (id, pid) AS (
   SELECT id, pid
   FROM Tags
   WHERE id = %(id)s
   UNION ALL
   SELECT c.id, c.pid
   FROM Tags c
     JOIN ancestors p ON p.pid = c.id
     WHERE c.id <> 0 -- prevent root tag
) 
SELECT *
FROM ancestors
ORDER BY pid
"""

sqlTree = """
SELECT id, pid
FROM TagsTree
WHERE id = %(id)s
ORDER BY pid
"""

errors = []
for tag in tags:
    curA = db.execute(sqlAncestor, {"id": tag["id"]})
    tagsA = curA.fetchall()
    curT = db.execute(sqlTree, {"id": tag["id"]})
    tagsT = curT.fetchall()
    for idx, tagA in enumerate(tagsA):
        try:
            if tagA["pid"] != tagsT[idx]["pid"]:
                errors.append(tag)
                break
        except IndexError:
            errors.append(tag)
            break

if errors:
    print(
        """
INCONSISTENT TAGS TREE
"""
    )
    for tag in errors:
        print(tag)

elif not args.quiet:
    print("No errors found")

db.close()
db2.close()
