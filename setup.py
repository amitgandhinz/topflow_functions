import os
import re
from setuptools import setup, find_packages

pip_requires = os.path.join(os.getcwd(), 'topflow/requirements.txt')

REQUIRES=[
    'datetime',
    'firebase_admin',
    'robin_stocks',
    'pyotp',
    'python-dateutil'
]

setup(
   name='topflow',
   version='1.0',
   description='An options tracker for top flow open interest',
   author='Amit Gandhi',
   author_email='amit@gandhi.co.nz',
   install_requires=REQUIRES,
   packages=['topflow'],
   scripts=[
        'topflow/serviceAccountKey.json'
   ]
)