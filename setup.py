import os
from setuptools import setup, find_packages


def get_version():
    try:
        return open(os.path.join('www', 'version.txt')).read().strip()
    except OSError:
        return 'n/a'


setup( name='gratipay'
     , version=get_version()
     , packages=find_packages()
     , entry_points = { 'console_scripts'
                      : [ 'payday=gratipay.cli:payday'
                        , 'fake_data=gratipay.utils.fake_data:main'
                         ]
                       }
      )
