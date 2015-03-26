from setuptools import setup, find_packages

from gratipay.version import get_version


setup( name='gratipay'
     , version=get_version()
     , packages=find_packages()
     , entry_points = { 'console_scripts'
                      : [ 'payday=gratipay.cli:payday'
                        , 'fake_data=gratipay.utils.fake_data:main'
                         ]
                       }
      )
