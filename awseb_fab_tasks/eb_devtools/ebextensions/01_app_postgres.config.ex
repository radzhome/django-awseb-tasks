packages:
  yum:
    libtiff-devel: ''
    libjpeg-devel: ''
    libzip-devel: ''
    freetype-devel: ''
    postgresql-devel: ''
    libmemcached: ''
    libmemcached-devel: ''
    cyrus-sasl-devel: ''
    zlib-devel: ''

container_commands:
  01_collectstatic:
    command: 'PYTHONPATH=.:..:../lib cd site/{project} && ./manage.py collectstatic -c --noinput && cd ../..'
    leader_only: true
  02_syncdb:
    command: 'PYTHONPATH=.:..:../lib cd site/{project} && ./manage.py syncdb --noinput && cd ../..'
    leader_only: true
  03_migrate:
    command: 'PYTHONPATH=.:..:../lib cd site/{project} && ./manage.py migrate --noinput && cd ../..'
    leader_only: true

option_settings:
  - namespace: aws:elasticbeanstalk:container:python
    option_name: WSGIPath
    value: site/{project}/wsgi.py
  - namespace: aws:elasticbeanstalk:container:python:staticfiles
    option_name: /static/
    value: site/{project}/static/
  - option_name: DJANGO_SETTINGS_MODULE
    value: settings_prod
