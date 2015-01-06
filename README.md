AWS Release Tasks
===============


Fabric release taks commands to use with AWS Beanstalk that wraps around boto.  Dependencies include git, fabric, prettytable and boto.  Optional dependency is django-storages, package includes utilities for setting up your static and media backend for use in S3.

TODO
-----
- at end of upload, query the environment till goes green but let user exit
- iterm the line does not go back up on upload %
- aws.config, remove creds functions

Feature Request
------------------
* Add ability to copy buckets
* Add ability to send local media files to bucket
* Log history

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
    from aws_tasks import tasks as aws


### S3 Storage

See Usage.
 
Assumptions
------------------

The project name is unique and the name of the project is derived via the union django-template project structure. To use in a different django project, how PROJECT_NAME is derived in the fabfile would change.
