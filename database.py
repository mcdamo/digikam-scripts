#!/usr/bin/python3

import configparser
import pymysql
import warnings

class Database:
    
    def __init__(self):
        config = configparser.ConfigParser()
        config.read('digikam.ini')
        conn = pymysql.connect(host=config['DATABASE']['HOST'],
          port=int(config['DATABASE']['PORT']),
          user=config['DATABASE']['USER'],
          passwd=config['DATABASE']['PASS'],
          db=config['DATABASE']['NAME'])
        conn.autocommit(False)
        # filter duplicate entry warnings
        warnings.filterwarnings('ignore', category=pymysql.Warning)
        self.conn = conn
        self.cur = self.conn.cursor();

    # wrap execute to catch SQL errors
    def execute(self, sql, args = None):
        try:
            self.cur.execute(sql, args)
            return self.cur
        except pymysql.Error as err:
            print(err)
            print(sql)
            exit()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()

    def sql(self):
        return self.cur._last_executed
