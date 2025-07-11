import os


def pytest_configure():
    os.system("sh ./restartDB_conf.sh")
