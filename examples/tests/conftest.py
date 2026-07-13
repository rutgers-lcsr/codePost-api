# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import os


def pytest_configure():
    os.system("sh ./restartDB_conf.sh")
