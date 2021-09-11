#!/usr/bin/env python3

import sys
import argparse
from digikam import Digikam


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


parser = argparse.ArgumentParser(description="Create Digikam Groups")
parser.add_argument(
    "path", metavar="PATH", type=str, help="relative album path or substring"
)
parser.add_argument(
    "-a",
    "--all",
    action="store_true",
    help="merge tags and rating between all items in group",
)
parser.add_argument(
    "-t", "--tags", action="store_true", help="clone tags from parent to children"
)
parser.add_argument(
    "-r",
    "--ratings",
    action="store_true",
    help="merge maximum rating to all items in group",
)
parser.add_argument("-c", "--commit", action="store_true", help="commit to database")
parser.add_argument(
    "-s",
    "--separator",
    dest="separator",
    default=".",
    type=str,
    help="filename prefix separator, default is '.'",
)
parser.add_argument(
    "-i",
    "--ignore",
    dest="ignore",
    action="append",
    type=str,
    help="ignore filenames containing this string from becoming a prefix. This argument can be repeated multiple times.",
)
parser.add_argument(
    "-g",
    "--group-version",
    dest="group_version",
    action="store_true",
    help="mark images as a 'version' of parent instead of grouping",
)
parser.add_argument(
    "-d",
    "--delete-groups",
    dest="delete_groups",
    action="store_true",
    help="delete groups for all images found in path. Default only deletes images that are put into new groups",
)

if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()
digikam = Digikam()
db = digikam.db()
groupType = "2"
if args.group_version:
    groupType = "1"

# find all unique name prefixes
sqlGroups = """
 SELECT SUBSTRING_INDEX(i.`name`, %(separator)s, '1') as namePrefix,
i.`album`,
a.`relativePath`
FROM Images i
INNER JOIN (
  SELECT * FROM Albums a
  WHERE a.`relativePath` like %(path)s
) a ON a.`id` = i.`album`
WHERE 1=1
{where}
GROUP BY namePrefix, i.`album`
ORDER BY i.`album`, namePrefix;
"""
if args.ignore:
    where = ""
    for i in args.ignore:
        where += "AND i.`name` NOT LIKE '%%{0}%%'".format(db.escape_like(i))
    sqlGroups = sqlGroups.format(where=where)
else:
    sqlGroups = sqlGroups.format(where="")
# find all files with matching prefix
# order by should put JPG before all other file types
sqlGroup = """
SELECT
i.`id`,
i.`name`,
%(prefix)s as namePrefix,
SUBSTRING_INDEX(i.`name`, '.', '1') as nameFull,
SUBSTRING_INDEX(i.`name`, '.','-1') as nameExt
FROM Images i
WHERE i.`album`=%(album)s
AND i.`name` LIKE %(match)s
{where}
ORDER BY namePrefix, nameFull, FIELD(nameExt,'JPG') desc;
"""
if args.ignore:
    where = ""
    for i in args.ignore:
        where += "AND i.`name` NOT LIKE '%%{0}%%'".format(db.escape_like(i))
    sqlGroup = sqlGroup.format(where=where)
else:
    sqlGroup = sqlGroup.format(where="")

sqlGroupDelete = """
DELETE FROM ImageRelations
WHERE `type` = %(type)s
AND (
  `object` IN %(ids)s
  OR `subject` IN %(ids)s
);
"""
sqlGroupIns = """
INSERT INTO ImageRelations (`object`, `subject`, `type`) VALUES 
"""
sqlRating = """
SELECT MAX(rating) as maxRating FROM ImageInformation WHERE imageid IN %(ids)s;
"""
sqlRatingsUpdate = """
UPDATE ImageInformation
SET rating = %(rating)s WHERE imageid IN %(ids)s;
"""
# clone from object to all subjects
sqlTagsClone = """
INSERT IGNORE INTO ImageTags (
  SELECT %(sub)s, it.tagid FROM ImageTags it
  INNER JOIN Tags t ON it.tagid = t.id
  WHERE imageid = %(obj)s
  AND t.pid <> 1
);
"""
# show additional tags subjects have that are not on object
sqlTagsAdditional = """
SELECT t.`id`, t.`name` FROM ImageTags it
INNER JOIN Tags t ON it.tagid = t.id
WHERE it.imageid = %(sub)s
AND it.tagid NOT IN (
  SELECT tagid FROM ImageTags WHERE imageid = %(obj)s
);
"""
# clone tags from all subjects except for internal tags (pid=1)
sqlTagsCloneAll = """
INSERT IGNORE INTO ImageTags (
  SELECT %(id)s, tagid FROM ImageTags it
  INNER JOIN Tags t ON it.tagid = t.id
  WHERE it.imageid IN %(ids)s
  AND it.imageid <> %(id)s
  AND t.pid <> 1
);
"""

cur = db.execute(
    sqlGroups,
    {"separator": args.separator, "path": "%" + db.escape_like(args.path) + "%"},
)

groups = []
for row in cur:
    groups.append(
        {
            "prefix": row["namePrefix"],
            "album": row["album"],
            "path": row["relativePath"],
        }
    )

path = ""
for group in groups:
    if path != group["path"]:
        print(group["path"])  # relativePath
        path = group["path"]
    prefix = group["prefix"]
    album = group["album"]
    cur = db.execute(
        sqlGroup,
        {"prefix": prefix, "album": album, "match": db.escape_like(prefix) + "%"},
    )
    imgs = []
    for row in cur:
        imgs.append({"id": row["id"], "name": row["name"]})
        # print(" - {0}".format(row))
    ids = list(str(i["id"]) for i in imgs)  # get ids from imgs
    if args.delete_groups or len(imgs) > 1:
        # purge items from any existing grouping
        # sql = sqlGroupDelete.format(ids = ",".join(ids))
        cur = db.execute(sqlGroupDelete, {"type": groupType, "ids": ids})
    if len(imgs) > 1:
        sql = sqlGroupIns
        subs = imgs.copy()
        obj = subs.pop(0)
        # shift first element
        names = list(str(i["name"]) for i in subs)
        print("\t{0} ({1})".format(obj["name"], ", ".join(names)))
        ins = []
        for img in subs:
            ins.append(
                "({obj}, {sub}, {type})".format(
                    obj=obj["id"], sub=img["id"], type=groupType
                )
            )
            # print("\t - {0}".format(img["name"]))
        sql += ",\n".join(ins)
        cur = db.execute(sql)
        # update ratings
        if args.ratings:
            # sql = sqlRating.format(ids=obj["id"])
            cur = db.execute(sqlRating, {"ids": ids})
            row = cur.fetchone()
            rating = row["maxRating"]
            print("\t  Updating rating: {0}".format(rating))
            subIds = list(str(i["id"]) for i in subs)
            # sql = sqlRatingsUpdate.format(rating=rating,ids=",".join(ids))
            cur = db.execute(sqlRatingsUpdate, {"rating": rating, "ids": ids})
        # clone tags from parent
        if args.tags:
            print("\t  Cloning parent's tags")
            for img in subs:
                # sql = sqlTagsAdditional.format(obj=obj["id"],sub=img["id"])
                cur = db.execute(
                    sqlTagsAdditional, {"obj": obj["id"], "sub": img["id"]}
                )
                extra = False
                # report on additional tags
                for row in cur:
                    if not extra:
                        print("\t    Child has additional tags, not cloning")
                    print("\t    {0} - {1}".format(img["name"], row["name"]))
                    extra = True
                # copy tags
                if extra == False:
                    # sql = sqlTagsClone.format(obj=obj["id"],sub=img["id"])
                    cur = db.execute(sqlTagsClone, {"obj": obj["id"], "sub": img["id"]})
        if args.all:
            print("\t  Merging all tags")
            # sql = sqlRating.format(ids=",".join(ids))
            cur = db.execute(sqlRating, {"ids": ids})
            row = cur.fetchone()
            rating = row["maxRating"]
            print("\t  Updating rating: {0}".format(rating))
            subIds = list(str(i["id"]) for i in subs)
            # sql = sqlRatingsUpdate.format(rating=rating,ids=",".join(ids))
            cur = db.execute(sqlRatingsUpdate, {"rating": rating, "ids": ids})
            for id in ids:
                # sql = sqlTagsCloneAll.format(id=id, ids=",".join(ids))
                cur = db.execute(sqlTagsCloneAll, {"id": id, "ids": ids})

if len(groups) > 0:
    if args.commit:
        eprint("Committing changes to database")
        db.commit()
    else:
        eprint("")
        eprint("Run script with -c switch to save to database")
db.close()
