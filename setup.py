from setuptools import setup, find_packages

setup( name='logstown'
     , packages=find_packages()
     , entry_points = { 'console_scripts'
                      : ['payday=logstown.cli:payday']
                       }
      )
