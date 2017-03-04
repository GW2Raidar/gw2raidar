GW2 Raidar
==========

Quickstart
----------

* Install Python 3
* `pip3 install django pandas`
* `python3 manage.py migrate`
* `python3 manage.py createsuperuser`
* `python3 manage.py runserver`
* Browse to http://localhost:8000/

(The migrate and createsuperuser steps can be replaced by
`bin/regen_db.sh`; also rerun this if database has changed
before going public.)
