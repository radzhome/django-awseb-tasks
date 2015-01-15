AWS Release Tasks
===============


Fabric release taks commands to use with AWS Beanstalk that wraps around boto.  Dependencies include git, fabric, prettytable and boto.  Optional dependency is django-storages, package includes utilities for setting up your static and media backend for use in S3.

TODO
-----
- sep. poll_env so can use it on other commands and sep.
- combine collect static / migrate commands with deploy
- logging (retrieve /var/log/* using fabric), ability to tail logs (see eb cli tool)
- template creation from config file / setup create new app / env based on options
- eb logs - re-create from eb cli and add
- eb init to generate custom templates for settings / wsgi py files

- cleanup memcached to be sep (Ask if memcached is required. These are the libs:
- 
    libmemcached: ''
    libmemcached-devel: ''
    cyrus-sasl-devel: ''
    zlib-devel: ''

- add check last error
boto: describe_events, see also create_configuration_template
```
                events = eb_client.describe_events(app_name,
                                                   env_name,
                                                   max_records=ServiceDefault.STATUS_EVENT_MAX_NUM,
                                                   severity=ServiceDefault.STATUS_EVENT_LEVEL)
                if len(events.result) > 0:
                    # Having one error event
                    for event in events.result:
                        msg = u'{0}\t{1}\t{2}'.format(event.event_date,
                                                      event.severity,
                                                      event.message)
                        log.info(u'Found last error event: {0}'.format(msg))
                        prompt.plain(msg)
```

Feature Request
------------------
* Add ability to copy buckets
* Add ability to send local media files to bucket
* Log history / descibe events:
* beanstalk.describe_events(application_name='kpmkhv', environment_name='kpmkhv-staging', max_records=100)
* 
Dependencies
-----

python:
* Fabric
* Django
* Boto
* prettytable

* git

Limitations
-----

The only fully supported db backend right now is postgres / postgis using the psycopg2 driver. The problem is that MySQL does not support all spatial operations, see the [https://docs.djangoproject.com/en/1.7/ref/contrib/gis/db-api/#mysql-spatial-limitations](django docs).  In the future ebextensions will be added to support mysql without spatial support in the future.

The current AMI the tool works with is ami-35792c5c. The yum packages often change, this being a legacy AMI, packages do come and go and the only way to freeze this is to create a custom AMI will all prerequisites installed. I will create such AMI in the near future and provide the ID.  Right now the ebextensions file installs all required packages as an instance is built.

History
-----

The tool required  AWS Elastic Beanstalk command line tool (eb) and boto. It is now its own separate tool. The original tool it relied on is here:  https://github.com/radlws/AWS-ElasticBeanstalk-CLI

Usage
-----

### Available commands

* list_environments  - Shows all available environments
* status - runs list_environments
* instances - Returns SSH connection string to available instance
* leader - Returns ssh connection string to leader instance
* list_instances - Shows all instances for an environment
* deploy - Deploy a release to the specified AWS Elastic Beanstalk environment. Requires site name & tag (release)
* dump_bucket - Downloads an S3 Bucket, given the bucket name
* manage - Run a manage command remotely, need host that you can get from leader command. use appropriate cert
* sw_creds - switch credential files for boto and eb if they exist in your home dir. Quickly switch accounts i.e kct and baker
* eb_init - creats aws.push and aws.config commands used by deploy
* new_creds
* generate_app_config - Generates .ebextensions/app.config file based on PROJECT_NAME in root of project
* environment_status:<env-name> - returns the environment health and status


### (OPTIONAL) Using the S3 backend for media and static (requires storages install). Add this to your settings file:

    DEFAULT_FILE_STORAGE = 'aws_tasks.storage_backends.MediaS3Storage'
    STATICFILES_STORAGE = 'aws_tasks.storage_backends.StaticS3Storage'
    THUMBNAIL_DEFAULT_STORAGE = DEFAULT_FILE_STORAGE


Installation
------------------

Please ensure the version of git you are using includes the points-at command, git 1.8+

### Add the package to your PYTHONPATH i.e. in  ../lib

You can include it anywhere so long as its accessible

    cd ../lib
    pip install --target . -U git+https://<username>@bitbucket.org/trapeze/aws-release-tasks.git

### Reference it in your fabfile.py

First set the required environment variables in your fab file, then import the tasks


    import os
    os.environ['PROJECT_NAME'] = os.getcwd().split('/')[-1]  # Import before aws_tasks, as it is used there.
    os.environ['DEFAULT_REGION'] = 'us-east-1'
    os.environ['DB_HOST'] = 'prod.your-db-url.us-east-1.rds.amazonaws.com'  # RDS DB URL, update accordingly']
    from aws_tasks import tasks as aws


### Sample Fabfile.py

    import os

    from fabric.api import task, local
    #env.project_name = os.getcwd().split('/')[-1]
    os.environ['PROJECT_NAME'] = os.getcwd().split('/')[-1]  # Import before aws_tasks, as it is used there.
    os.environ['DEFAULT_REGION'] = 'us-east-1'
    os.environ['DB_HOST'] = 'prod.czxygluip2xt.us-east-1.rds.amazonaws.com'  # RDS DB URL, update accordingly']
    from awseb_tasks import tasks as aws


### S3 Storage

See Usage.
 
Example Usage
------------------

Assuming tasks are imported as aws. You can deploy, migrate and collectstatic like this:

    fab aws.deploy aws.leader aws.manage:migrate aws.manage:collectstatic
    
the 'leader' task stores the leader instance in env.hosts, manage makes an ssh connection which requires you use the correct ssh private key used to start the instance to connect to it. Make sure the ssh key is added to ssh agent so it gets picked up:

    chmod 600 ~/.ssh/id_rsa_aws 
    ssh-add ~/.ssh/id_rsa_aws 


Assumptions
------------------

The project name is unique and the name of the project is also used as the name of the application in Elastic Beanstalk. The site i.e. live, staging, content, are created in EB as project-site.
