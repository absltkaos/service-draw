from setuptools import setup, find_packages

setup(
   name='servicedraw',
   version='1.0.0',
   description='Module for generating graphs from .ini style configs using pydot',
   author='Dan Farnsworth',
   author_email='absltkaos@gmail.com',
   packages=find_packages(),
   install_requires=[
       'dateutil'
   ],
)
