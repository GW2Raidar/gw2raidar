GW2 Raidar
==========

Quickstart
----------

* Install Python 3 and pip3
* `pip install django pandas requests django-taggit psycopg2 django-cors-headers djangorestframework django-rest-swagger django-postgres-fuzzycount django-static-compress`
* Optionally for development, `pip3 install django-debug-toolbar django-debug-toolbar-request-history`
* `python3 manage.py migrate`
* `python3 manage.py createsuperuser`
* `python3 manage.py runserver`
* Browse to http://localhost:8000/

To generate statistics, use `python3 manage.py restat [-f] [-v{0,1,2,3}]`.

To process new uploads, use `python3 manage.py process_uploads [-v{0,1,2,3}]`.

Apache config:

```
WSGIPassAuthorization On

Alias /static/ /var/www/apps/gw2raidar/static/                                                                      
WSGIDaemonProcess gw2raidar processes=3 threads=4 display-name=%{GROUP} python-path=/var/www/apps/gw2raidar
WSGIProcessGroup gw2raidar
WSGIScriptAlias / /var/www/apps/gw2raidar/gw2raidar/wsgi.py process-group=gw2raidar

<Directory /var/www/apps/gw2raidar/gw2raidar>
    LimitRequestBody 26214400
    <Files wsgi.py>
        Require all granted
    </Files>
</Directory>

<Directory /var/www/apps/gw2raidar/static>
    ExpiresActive on
    ExpiresDefault "access plus 1 year"
    Header append Cache-Control public
</Directory>

<Location /static/>
    RewriteEngine on
    RewriteCond %{HTTP:Accept-Encoding} \b(x-)?gzip\b
    RewriteCond %{REQUEST_FILENAME}.gz -s
    RewriteRule ^(.+) $1.gz [L]
</Location>

# Also add a content-encoding header to tell the browser to decompress

<FilesMatch \.css\.gz$>
    ForceType text/css
    Header set Content-Encoding gzip
</FilesMatch>

<FilesMatch \.js\.gz$>
    ForceType text/javascript
    Header set Content-Encoding gzip
</FilesMatch>
```
