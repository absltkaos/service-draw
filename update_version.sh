#!/bin/bash
vers=$1

if [ -z "$vers" ] ; then
    echo "$(basename) VERSION"
    exit 1
fi

#Update setup.py
echo "Updating setup.py"
sed -i "s/version=.\+/version='${vers}',/" ./setup.py

#Update version in module
echo "Updating versions in python"
sed -i "s/^__version__=.\+/__version__='${vers}'/" servicedraw/__init__.py
sed -i "s/^__version__=.\+/__version__='${vers}'/" service-draw.py

#Update package dependency on module version
echo "Updating package dependency to module"
sed -i "s/^\(Depends:.*, python3-servicedraw \)(.*)\(.*\)$/\1(>= ${vers})\2/g" debian/control
