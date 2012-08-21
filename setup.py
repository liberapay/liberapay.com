from setuptools import setup, find_packages
from gittip import __version__

setup( name='gittip'
     , version=__version__
     , packages=find_packages()
     , entry_points = { 'console_scripts'
                      : [ 'payday=gittip.cli:payday'
                        , 'swaddle=gittip.swaddle:main'
                         ]
                       }
      )
