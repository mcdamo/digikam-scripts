#!/usr/bin/env python3

import sys
import argparse
import progressbar
import tabulate
from getkey import getkey
from digikam import Digikam


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


parser = argparse.ArgumentParser(description="Create Digikam Tags for Camera and Lens")
parser.add_argument(
    "path", metavar="PATH", type=str, help="relative album path or substring"
)

if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()
digikam = Digikam()
config = digikam.config.tags()
db = digikam.db()

# path should match a single relativePath
sqlPath = """
SELECT r.label, a.relativePath FROM `Albums` a 
INNER JOIN `AlbumRoots` r ON r.id = a.albumRoot
WHERE a.relativePath like %(path)s
ORDER BY r.label, a.relativePath
"""

cur = db.execute(sqlPath, {"path": "%" + db.escape_like(args.path) + "%"})
if cur.rowcount == 0:
    print("Path not found")
    sys.exit(2)
paths = cur.fetchall()

print(tabulate.tabulate(paths))

print("Continue (y/n) ? ")
s = getkey()
if s != "y":
    sys.exit(-1)

# find Tag ids for root
root_camera = config["root_camera"]
root_lens = config["root_lens"]
makes = config["makes"]

new_tags_list = []


class TagNotFoundException(Exception):
    pass


class MultipleTagsException(Exception):
    pass


def fetchTag(name, pid=None):
    sql = "SELECT id FROM `Tags` WHERE `name` = %(name)s"
    if pid:
        sql = sql + " AND `pid` = %(pid)s"
    cur = db.execute(sql, {"name": name, "pid": pid})
    if cur.rowcount == 0:
        raise TagNotFoundException("Root tag not found: %s" % name)
    elif cur.rowcount >= 2:
        raise MultipleTagsException("Multiple tags found: %s" % name)

    return cur.fetchone()


def createTag(name, pid):
    sql = "INSERT INTO `Tags` (`name`, `pid`) VALUES (%(name)s, %(pid)s)"
    cur = db.execute(sql, {"name": name, "pid": pid})
    new_tags_list.append((cur.lastrowid, pid, name))
    # TagsTree records are created by a Trigger on Tags table
    return cur.lastrowid


def fetchOrCreateTag(name, pid):
    try:
        return fetchTag(name, pid)
    except TagNotFoundException:
        id = createTag(name, pid)
        return {"id": id}


def addImageTag(imageid, tagid):
    sql = "INSERT INTO `ImageTags` (`imageid`, `tagid`) VALUES (%(imageid)s, %(tagid)s)"
    cur = db.execute(sql, {"imageid": imageid, "tagid": tagid})
    return cur


try:
    root_camera_tag_id = fetchTag(root_camera, 0)["id"]
    root_lens_tag_id = fetchTag(root_lens, 0)["id"]
except Exception as e:
    eprint(e)
    sys.exit(3)


# ignore any photos with existing tags under these roots
# videos do not have ImageMetadata
sql = """
SELECT
i.id,
CONCAT(SUBSTRING_INDEX(a.relativePath, '/', -1), '/', i.name) as path,
im.make,
im.model,
im.lens
FROM `Images` i
INNER JOIN `ImageMetadata` im ON im.imageid = i.id
INNER JOIN (
    SELECT * FROM `Albums` a
    WHERE a.relativePath like %(path)s
) a ON a.id = i.album
WHERE 1=1
AND NOT EXISTS (
    SELECT it.imageid
    FROM `ImageTags` it
    INNER JOIN `Tags` t ON t.id = it.tagid
    WHERE
        imageid = i.id
        AND t.pid IN %(roots)s
)
ORDER BY a.relativePath, i.album
"""

cur = db.execute(
    sql,
    {
        "path": "%" + db.escape_like(args.path) + "%",
        "roots": (
            root_camera_tag_id,
            root_lens_tag_id,
        ),
    },
)
## tabulate named fields https://github.com/astanin/python-tabulate/issues/36#issue-553238535
# def table(table_data, headers):
#    result_data = [{k: t[k] for k in t if k in headers} for t in table_data]
#    if not isinstance(headers, dict):
#        headers = {h: h for h in headers}
#    return tabulate(result_data, headers=headers)
# print(table(rows, ["name", "make", "model", "lens"]))


images = cur.fetchall()


def decodeMetadata(metadata, makes):
    make = metadata["make"]
    model = metadata["model"]
    lens = metadata["lens"]
    if not make or not model:
        return {
            "make": None,
            "model": None,
            "lens": None,
        }

    # fix differently named makes
    fixMakes = {
        "LG Electronics": "LG",
        "lge": "LG",
        "LGE": "LG",
        "NIKON CORPORATION": "NIKON",
        "OLYMPUS CORPORATION": "OLYMPUS",
        "OLYMPUS IMAGING CORP.": "OLYMPUS",
        "OLYMPUS OPTICAL CO.,LTD": "OLYMPUS",
    }
    if fixMakes.get(make, False):
        make = fixMakes[make]

    # prepend make to model if not included
    if not model[: len(make)] == make:
        model = make + " " + model

    def decodeLens(make, lens, makes):
        if not lens:
            return None
        # ignore lenses if not these makes
        if len(makes) > 0 and not make in makes:
            return None

        # ignore Canon lenses that begin with a number
        if lens[0].isdigit():
            return None

        # fix inconsistently named lenses:
        fixLens = {
            "Canon EF-S 17-85mm f4-5.6 IS USM": "Canon EF-S 17-85mm f4-5.6 IS USM",
            "EF-S18-55mm f/3.5-5.6 IS": "Canon EF-S 18-55mm f3.5-5.6 IS",
            "EF24-105mm f/4L IS USM": "Canon EF 24-105mm f4L IS USM",
            "Canon EF 24-105mm f/4L IS": "Canon EF 24-105mm f4L IS USM",
            "EF50mm f/1.4 USM": "Canon EF 50mm f1.4 USM",
        }
        if fixLens.get(lens, False):
            return fixLens[lens]

        # strip slashes in tags (common with Canon lenses)
        lens = lens.replace("/", "")

        # prepend make to lens if not included
        if not lens[: len(make)] == make:
            return make + " " + lens
        return lens

    lens = decodeLens(make, lens, makes)
    return {
        "make": make,
        "model": model,
        "lens": lens,
    }


images = [{**i, **decodeMetadata(i, makes)} for i in images]
print(tabulate.tabulate(images, headers="keys", tablefmt="psql"))

# optimized to reuse id
prev_image = {
    "make": None,
    "model": None,
    "lens": None,
}
camera_base = None
camera_base_id = None
lens_base = None
lens_base_id = None
print("")
print("Processing Images")
for image in progressbar.progressbar(images):
    if image["make"] and image["model"]:
        if image["make"] != prev_image["make"]:
            # find tags under root tags
            camera_base = image["make"] + " Camera"
            camera_base_id = fetchOrCreateTag(camera_base, root_camera_tag_id)["id"]
        if image["make"] != prev_image["make"] or image["model"] != prev_image["model"]:
            model_id = fetchOrCreateTag(image["model"], camera_base_id)["id"]

        addImageTag(image["id"], root_camera_tag_id)
        addImageTag(image["id"], camera_base_id)
        addImageTag(image["id"], model_id)
        if image["lens"]:
            if not lens_base_id or image["make"] != prev_image["make"]:
                lens_base = image["make"] + " Lens"
                lens_base_id = fetchOrCreateTag(lens_base, root_lens_tag_id)["id"]
            if (
                not lens_id
                or image["make"] != prev_image["make"]
                or image["lens"] != prev_image["lens"]
            ):
                lens_id = fetchOrCreateTag(image["lens"], lens_base_id)["id"]

            if root_lens_tag_id != root_camera_tag_id:
                addImageTag(image["id"], root_lens_tag_id)
            addImageTag(image["id"], lens_base_id)
            addImageTag(image["id"], lens_id)
        else:
            lens_base_id = None
            lens_id = None
    prev_image = image


# confirm for any new models or makes added to DB
print("")
print("NEW TAGS (id, pid, name)")
print(
    tabulate.tabulate(
        [{"Num": i + 1, "Name": new_tags_list[i]} for i in range(len(new_tags_list))]
    )
)
print("Commit changes (y/n) ? ")
s = getkey()
if s != "y":
    db.rollback()
    db.close()
    sys.exit(-1)
db.commit()
db.close()
