#!/usr/bin/env bash

cd vendor

cd numpy
python setup.py install
cd ..

pip install scipy

cd oosuite
python setup.py install
cd ..

cd cvxopt/src/
python setup.py install
cd ../..

