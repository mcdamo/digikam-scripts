#!/usr/bin/python3

# Check the consistency of Digikam's Tags table
# prints nothing if consistent
# prints inconsistent tags if found

import sys
import argparse
from database import Database

parser = argparse.ArgumentParser(description='Check Digikam Tags Tree')
parser.add_argument('-q', '--quiet', action='store_true', help="quiet, don't output if tree ok")
parser.add_argument('-c', '--commit', action='store_true', help='commit rebuild to database')

args = parser.parse_args()

def errorProc(type, name):
    print("""Database {type} '{name}' is not found.
Check your database for the {type} or run the provided SQL script to create the {type}."""
        .format(type=type, name=name))
    sys.exit(1)

def errorDesc():
    print("""
INCONSISTENT TAGS TREE
Recommend running this script with -c switch to rebuild tags tree.
""")

db = Database()
conn = db.conn
# check for required database procedures
name="tags_rebuild"
sqlProcedure="SHOW PROCEDURE STATUS WHERE `Db`=%(db)s AND `Name`=%(name)s;"
cur = db.execute(sqlProcedure, {'db': conn.db, 'name':name})
if cur.fetchone() == None:
    errorProc("procedure", name)
name="hierarchy_connect_by_parent_eq_prior_id"
sqlFunction="SHOW FUNCTION STATUS WHERE `Db`=%(db)s AND `Name`=%(name)s;"
cur = db.execute(sqlFunction, {'db': conn.db, 'name':name})
if cur.fetchone() == None:
    errorProc("function", name)


cur = db.execute("SELECT id,name,pid,lft,rgt FROM `Tags`;")
tags = cur.fetchall()

sql = """SELECT sub.* FROM
(
  SELECT *
    FROM `Tags` nt0
  ) sub
  INNER JOIN `Tags` nt1
  LEFT JOIN
  (
    SELECT  hierarchy_connect_by_parent_eq_prior_id(id) AS id
    FROM    (
                SELECT  @start_with := {id},
                        @id := @start_with,
                        @level := 1
                ) vars, `Tags`
        WHERE   @id IS NOT NULL
    ) sub2 ON sub2.id = sub.id
 
  WHERE nt1.id = {id}
  AND ((sub.`lft` > nt1.`lft` AND sub.`lft` <= nt1.`rgt`)
   OR (sub.`rgt` > nt1.`lft` AND sub.`rgt` < nt1.`rgt`))
  AND sub2.`id` IS NULL
;
"""
flag = False
for tag in tags:
    id = tag[0]
    cur = db.execute(sql.format(id = id))
    for row in cur:
        if(not flag):
            print("Overlapped tags:")
        flag = True
        print(" - {0} {1}".format(tag,row))

if not flag and not args.quiet:
    print("No errors found")
if flag:
    if args.commit:
        print("Committing changes to database")
        sql="CALL tags_rebuild();"
        cur = db.execute(sql)
        db.commit() # not required for db PROCEDURE
    else:
         errorDesc()

db.close()
