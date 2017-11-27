__author__ = 'Larry'

'''
Deployment toolkit.
'''

import os, re

from datetime import datetime
from fabric.api import *

# 服务器登录用户名
env.user = 'ubuntu'
# sudo用户为ubuntu
env.sudo_user = 'ubuntu'
# 服务器地址，可以有多个，依次部署
env.hosts = ['111.230.133.70']

# 服务器MySQL用户名和口令
db_user = 'www-data'
db_password = 'www-data'

_TAR_FILE = 'dist-awesome.tar.gz'

def build():
    includes = ['static', 'templates', ]

