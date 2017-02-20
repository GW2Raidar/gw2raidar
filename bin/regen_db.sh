#!/bin/bash

cd $(dirname "$0")/..
rm db.sqlite3
python3 manage.py migrate
python3 manage.py createsuperuser

echo "After this, you may want to"
echo "python3 manage.py runserver"
