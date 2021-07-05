#!/usr/bin/python3

import sys
import argparse
from database import Database
from tabulate import tabulate


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
db = Database()

# path should match a single relativePath
sqlPath = """
SELECT r.label, a.relativePath FROM Albums a 
INNER JOIN AlbumRoots r ON r.id = a.albumRoot
WHERE a.relativePath like %(path)s
ORDER BY r.label, a.relativePath
"""

cur = db.execute(sqlPath, {"path": "%" + db.escape_like(args.path) + "%"})
if cur.rowcount == 0:
    print("Path not found")
    sys.exit(2)
paths = cur.fetchall()

print(tabulate(paths))

s = input("Continue (y/n) ? ")
if s != "y":
    sys.exit(0)

# find Tag ids for root
root_camera = "_Camera"


class TagNotFoundException(Exception):
    pass


class MultipleTagsException(Exception):
    pass


def fetchTagByName(name, pid=None):
    sql = "SELECT id FROM Tags WHERE name = %(name)s"
    if pid:
        sql = sql + " AND pid = %(pid)s"
    cur = db.execute(sql, {"name": name, "pid": pid})
    if cur.rowcount == 0:
        raise TagNotFoundException("Camera root not found")
    elif cur.rowcount >= 2:
        raise MultipleTagsException("Multiple Camera roots")

    return cur.fetchone()


try:
    root_tag_id = fetchTagByName(root_camera)["id"]
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
FROM Images i
INNER JOIN ImageMetadata im ON im.imageid = i.id
INNER JOIN (
    SELECT * FROM Albums a
    WHERE a.relativePath like %(path)s
) a ON a.id = i.album
WHERE 1=1
AND NOT EXISTS (
    SELECT it.imageid
    FROM ImageTags it
    INNER JOIN Tags t ON t.id = it.tagid
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
        "roots": (root_camera_id),
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


def decodeMetadata(metadata):
    make = metadata["make"]
    model = metadata["model"]
    lens = metadata["lens"]

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

    def decodeLens(make, lens):
        if not lens:
            return None
        # ignore lenses if not these makes
        makes = {"Canon", "FUJIFILM"}  # set()
        if not make in makes:
            return None

        # ignore Canon lenses that begin with a number
        if lens[0].isdigit():
            return None

        # fix differently named lenses:
        fixLens = {
            "Canon EF-S 17-85mm f4-5.6 IS USM": "Canon EF-S 17-85mm f/4-5.6 IS USM",
            "EF-S18-55mm f/3.5-5.6 IS": "Canon EF-S 18-55mm f/3.5-5.6 IS",
            "EF24-105mm f/4L IS USM": "Canon EF 24-105mm f/4L IS USM",
            "Canon EF 24-105mm f/4L IS": "Canon EF 24-105mm f/4L IS USM",
            "EF50mm f/1.4 USM": "Canon EF 50mm f/1.4 USM",
        }
        if fixLens.get(lens, False):
            return fixLens[lens]

        # prepend make to lens if not included
        if not lens[: len(make)] == make:
            return make + " " + lens
        return lens

    lens = decodeLens(make, lens)
    return {
        "make": make,
        "model": model,
        "lens": lens,
    }


images = [{**i, **decodeMetadata(i)} for i in images]
print(tabulate(images, headers="keys"))

# optimized to reuse id
prev_image = None
camera_base = None
camera_base_id = None
lens_base = None
lens_base_id = None
for image in images:
    if image["make"] and image["model"]:
        if not prev_image or image["make"] != prev_image["make"]:
            # find tags under root tags
            camera_base = image["make"] + " Camera"
            try:
                camera_base_id = fetchTagByName(camera_base, root_tag_id)["id"]
            except TagNotFoundException:
                # FIXME create base tag
                # FIXME create TagsTree records?
                pass
        if (
            not prev_image
            or image["make"] != prev_image["make"]
            or image["model"] != prev_image["model"]
        ):
            try:
                model_id = fetchTagByName(image["model"], camera_base_id)["id"]
            except TagNotFoundException:
                # FIXME create model tag
                # FIXME create TagsTree records?
                pass
        if image["lens"]:
            if not prev_image or image["make"] != prev_image["make"]:
                lens_base = image["make"] + " Lens"
                try:
                    lens_base_id = fetchTagByName(lens_base, root_tag_id)["id"]
                except TagNotFoundException:
                    # FIXME create base tag
                    # FIXME create TagsTree records?
                    pass
            if (
                not prev_image
                or image["make"] != prev_image["make"]
                or image["lens"] == prev_image["lens"]
            ):
                try:
                    lens_id = fetchTagByName(image["lens"], lens_base_id)["id"]
                except TagNotFoundException:
                    # FIXME create model tag
                    # FIXME create TagsTree records?
                    pass
    prev_image = image


# FIXME confirm for any new models or makes added to DB
# FIXME add tags to images in DB

db.close()
