How to pull off the WSGI+PostgreSQL deploy

```
apt install python3-dev python3-pip apache2 apache2-dev git postgresql-9.6
```

Create the postgres user

```
sudo -u postgres psql
CREATE ROLE [user] LOGIN PASSWORD '[password]';
CREATE DATABASE [database] WITH OWNER = [user];
```

Download `mod_wsgi` source

```
sudo su -
wget [mod_wsgi_url]
tar xzf [mod_wsgi].tar.gz
cd [mod_wsgi_dir]
./configure --with-python=`which python3`
make
make install
```


create `/etc/apache2/mods-available/wsgi.load`:

```
LoadModule wsgi_module /usr/lib/apache2/modules/mod_wsgi.so
WSGIApplicationGroup %{GLOBAL}
```

Then

```
a2enmod wsgi
certbot --apache
```

Assume the app will be called `gw2r-test`.
Put the following into `/etc/apache2/sites-enabled/000-default-le-ssl.conf`, somewhere inside `VirtualHost`:

```
Alias /gw2r-test/static/ /var/www/apps/gw2r-test/static/
WSGIDaemonProcess gw2r-test processes=2 threads=15 display-name=%{GROUP} python-path=/var/www/apps/gw2r-test
WSGIProcessGroup gw2r-test
WSGIScriptAlias /gw2r-test /var/www/apps/gw2r-test/gw2raidar/wsgi.py process-group=gw2r-test
<Directory /var/www/apps/gw2r-test/gw2raidar>
    <Files wsgi.py>
        Require all granted
    </Files>
</Directory>
```

Get GW2Raidar (assuming `develop` branch):

```
mkdir /var/www/apps
cd /var/www/apps
git clone git@github.com:merforga/gw2raidar.git -b develop gw2r-test
cd gw2r-test
cp gw2raidar/settings_local.py.example gw2raidar/settings_local.py
```

Edit `gw2raidar/settings_local.py` to prepare for WSGI:

```
DEBUG = False

# When DEBUG is False (must for production),
# this needs to be set for the app's host, like so:
ALLOWED_HOSTS = ['139.162.68.156']

# This needs to be secret and can't be committed to the repository
SECRET_KEY = '[secretkey]'

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'gw2r_test',
        'USER': 'gw2raidar',
        'PASSWORD': '[password]',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}

EMAIL_SUBJECT_PREFIX = '[gw2raidar] '

# normal mail (like password reset), to users
DEFAULT_FROM_EMAIL = 'gw2raidar@example.com'

# error emails, to admins
SERVER_EMAIL = 'gw2raidar@example.com' #

# the abovementioned admins
# ADMINS = [
#         ('Admin1', 'admin1@example.com'),
#         ('Admin2', 'admin2@example.com'),
#     ]


# SMTP server
# You can use a fake SMTPD that will print any "sent" emails to console:
#
#     python -m smtpd -n -c DebuggingServer localhost:1025
#
# This would require 'EMAIL_PORT = 1025`.
# Obviously, in production, point it to a real SMTP server, where the default
# `EMAIL_PORT = 25` should be okay.
EMAIL_HOST = 'localhost'
# EMAIL_PORT = 1025

STATIC_URL = '/gw2r-test/static/'
STATIC_ROOT = '/var/www/apps/gw2r-test/static/'
```


# Adding a user

```
useradd -m amadan
passwd amadan
mkdir ~amadan/.ssh
cd ~amadan/.ssh
cat > authorized_hosts
chown amadan:amadan . authorized_hosts
chmod og-rwx . authorized_hosts
usermod -aG sudo amadan

