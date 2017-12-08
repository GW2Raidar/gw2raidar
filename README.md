GW2 Raidar
==========

Quickstart
----------

* Install Python 3 and pip3
* `pip3 install django pandas requests django-taggit psycopg2`
* Optionally for development, `pip3 install django-debug-toolbar django-debug-toolbar-request-history`
* `python3 manage.py migrate`
* `python3 manage.py createsuperuser`
* `python3 manage.py runserver`
* Browse to http://localhost:8000/

To generate statistics, use `python3 manage.py restat [-f] [-v{0,1,2,3}]`.

To process new uploads, use `python3 manage.py process_uploads [-v{0,1,2,3}]`.
