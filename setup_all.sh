#!/usr/bin/env bash

cd vendor

cd numpy
python setup.py install
cd ..

pip install scipy

cd oosuite
python setup.py instal
cd ..

cd cvxopt/src/
python setup.py install
cd ../..

