from setuptools import setup, find_packages
from logstown import __version__

setup( name='logstown'
     , version=__version__
     , packages=find_packages()
     , entry_points = { 'console_scripts'
                      : ['payday=logstown.cli:payday']
                       }
      )
