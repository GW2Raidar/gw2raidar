![image](https://user-images.githubusercontent.com/25611469/41951681-7079a9d0-7a0f-11e8-89f2-99967dadaf64.png)
==========

Vision
----------
To be the go to site for Guild Wars 2 raid and fractal insights

Introduction
----------
GW2 Raidar is a web application to parse [ARCDPS log files](https://deltaconnected.com/arcdps/) for Guild Wars 2. In addition, nearly all metrics and statistics are compiled into a global database for comparison and further insights. 

https://www.gw2raidar.com

Due to time constraints and the ever increasing list of features and requests, we have decided to finally go open source to hopefully speed up the development of certain new features as well as speedy fixing of bugs encountered. Feature requests and bug reports are welcome! You can submit them via our [Discord](http://discord.gg/8j43kAc) or [issues log](https://github.com/merforga/gw2raidar/issues)

Contributing
----------
Almost anyone can contribute to this project. The main issue comes down to understanding the relationship and linking between all facets of the application and the limited system resources available to do it. In order for your contribute to be implemented, we require the following:

* Knowledge of basic game mechanics and interactions
* Understanding of the GW2R spec
* Understanding of the ARCDPS log file spec
* Understanding of Python and / or willingness to learn
* Tenacity and perserverence to actually implement the change

To start, head on over to the [Wiki](https://github.com/merforga/gw2raidar/wiki) where the GW2R documentation and contribution guildelines sit. 

Quickstart Guide
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

License
----------
See the [License](https://github.com/merforga/gw2raidar/blob/master/LICENSE.md) file
