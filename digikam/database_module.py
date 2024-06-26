import pymysql
import warnings


class Database:
    def __init__(self, config):
        conn = pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            passwd=config["passwd"],
            db=config["db"],
            charset="utf8",
        )
        conn.autocommit(False)
        # filter duplicate entry warnings
        warnings.filterwarnings("ignore", category=pymysql.Warning)
        self.conn = conn
        self.cur = self.conn.cursor(pymysql.cursors.DictCursor)

    # escape special characters for LIKE queries
    def escape_like(self, sql):
        return self.conn.escape_string(sql).replace("_", "\\_")

    # wrap execute to catch SQL errors
    def execute(self, sql, args=None):
        try:
            # store sql and args incase we want to inspect with sql()
            self._last_sql = sql
            self._last_args = args
            self.cur.execute(sql, args)
            return self.cur
        except pymysql.Error as err:
            print(err)
            print(self.sql())
            exit()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.cur.close()
        self.conn.close()

    # returns the last SQL query called
    def sql(self):
        return self.cur.mogrify(self._last_sql, self._last_args)
