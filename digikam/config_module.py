import configparser


class Config:
    def __init__(self, filename):
        config = configparser.ConfigParser()
        config.read(filename)
        self._config = config

    def database(self):
        config = self._config
        return {
            "host": config["DATABASE"]["HOST"],
            "port": int(config["DATABASE"]["PORT"]),
            "user": config["DATABASE"]["USER"],
            "passwd": config["DATABASE"]["PASS"],
            "db": config["DATABASE"]["NAME"],
        }

    def tags(self):
        config = self._config
        return {
            "root_camera": config["TAGS"]["ROOT_CAMERA"],
            "root_lens": config["TAGS"]["ROOT_LENS"],
            "makes": config["TAGS"]["MAKES"].split(","),
        }
