from digikam import Config
from digikam import Database


class Digikam:
    def __init__(self):
        self._config = Config("digikam.ini")

    @property
    def config(self):
        return self._config

    # return a new database connection each call
    def db(self):
        return Database(self.config.database())
