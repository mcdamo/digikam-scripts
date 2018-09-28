# digikam-scripts
A collection of experimental scripts for manipulating the Digikam database.

These only work on an external MySQL/MariaDB instance. They will not work if you are using sqlite or the Digikam Internal MySQL.

Make a backup of your database before testing and *Use At Your Own Risk*. 

## Setup
These scripts require python3 and pymysql.

Copy ```digikam.ini.dist``` to ```digikam.ini``` and populate with your database connection settings.

## digikam-group.py
This script has many options for creating Groups and merging Tags and Rating between items in these Groups.

Call this script with a path or substring, it will search for that path in your Digikam albums and then locate images within this album. Multiple albums may be retrieved if your given path is a substring.
```
positional arguments:
  PATH                  relative album path or substring

optional arguments:
  -h, --help            show this help message and exit
  -a, --all             merge tags and rating between all items in group
  -t, --tags            clone tags from parent to children
  -r, --ratings         merge maximum rating to all items in group
  -c, --commit          commit to database
  -s SEPARATOR, --separator SEPARATOR
                        filename prefix separator, default is '.'
  -i, --ignore IGNORE    ignore filenames containing this string from becoming
                        a prefix
  -g, --group-version     mark images as a 'version' of parent instead of
                        grouping
  -d, --delete-groups     delete groups for all images found in path. Default
                        only deletes images that are put into new groups
```
**This script does not update your images.** After committing changes to database you should write metadata to images using Digikam.

## digikam-tags-check.py
This script will find and report when the Tags nested set tree structure is in an inconsistent state. If errors are found then you can choose to rebuild the entire tree using the provided procedure.
### Database setup
A pre-requisite of this script is for you to install the necessary helper procedures to the database.

Install helpers with ```mysql -D digikam_core < digikam-tags-check.sql```

The hierarchy function is adapted from [Explain Extended](https://explainextended.com/2009/03/17/hierarchical-queries-in-mysql/) and the tree rebuild procedure adapted from [this post](https://stackoverflow.com/a/3634268).
