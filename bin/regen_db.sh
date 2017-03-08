#!/bin/bash

email="$1"
name="$2"
password="$3"

cd $(dirname "$0")/..
rm -f db.sqlite3
dbengine=$(python3 -c "from gw2raidar.settings import DATABASES; print(DATABASES['default']['ENGINE'])")
if [[ "$dbengine" == "django.db.backends.postgresql" ]]; then
  dbname=$(python3 -c "from gw2raidar.settings import DATABASES; print(DATABASES['default']['NAME'])")
  dbuser=$(python3 -c "from gw2raidar.settings import DATABASES; print(DATABASES['default']['USER'])")
  dropdb $dbname
  createdb $dbname -O $dbuser
elif [[ "$dbengine" -eq "django.db.backends.sqlite3" ]]; then
  dbname=$(python3 -c "from gw2raidar.settings import DATABASES; print(DATABASES['default']['NAME'])")
  rm $dbname
fi
python3 manage.py migrate
if [[ "$email" == "-n" ]]; then
  echo Skipping superuser
elif [[ -z "$password" ]]; then
  echo Superuser:
  python3 manage.py createsuperuser
else
  echo "from django.contrib.auth.models import User; User.objects.create_superuser('$name', '$email', '$password')" | python3 manage.py shell > /dev/null
fi

echo "After this, you may want to"
echo "python3 manage.py runserver"
