#!/usr/bin/env bash

cd vendor

pip install numpy
#cd numpy
#python setup.py install
#cd ..

#pip install scipy

pip install openopt
# cd oosuite
# python setup.py install
# cd ..

cd glpk
tar -xvf glpk-4.44.tar.gz
cd glpk-4.44
./configure
make install
cd ../..

cd cvxopt/src/
python setup.py install
cd ../..

