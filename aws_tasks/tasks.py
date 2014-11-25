"""
Fabric tasks for interacting with AWS services using boto and eb tool, as well as prettytable for output.

"""
import datetime
import itertools
import os
import re

import boto
import boto.beanstalk
import boto.ec2
import boto.ec2.autoscale
import boto.exception
import boto.rds2
from fabric import colors
from fabric.api import env, task, run
from fabric.operations import local
from fabric.context_managers import hide, cd
import prettytable

from decorators import args_required


# Items set via FabFile, required for most of the stuff to work
DEFAULT_REGION = os.environ.get('DEFAULT_REGION', 'us-east-1')
PROJECT_NAME = os.environ.get('PROJECT_NAME')
DB_HOST = os.environ.get('DB_HOST')

# Pretty Table color settings
CLEAR_SCREEN = '\x1b[2J\x1b[H'
COLOR_FNS = {
    'Green': colors.green,
    'Red': lambda s: colors.red(s, bold=True),
    'Yellow': colors.yellow,
}
INSTANCE_STATE_FNS = {
    'running': colors.green,
    'terminated': lambda s: colors.red(s, bold=True),
    'stopped': lambda s: colors.red(s, bold=True),
    'stopping': colors.yellow,
    'pending': colors.blue,
    'shutting-down': colors.yellow,
}

######################## From Fabfile.py, moved here


#Defines the S3 Buckets based on the project name and the environment
S3_BUCKETS = {
    'staging': '%s-staging' % os.environ['PROJECT_NAME'],
    'live': '%s' % os.environ['PROJECT_NAME'],
    'qa': '%s-qa' % os.environ['PROJECT_NAME'],
    #'content': '%s-content' % os.environ['PROJECT_NAME'],  # used for testing
}


@task
@args_required(('site_name', 'e.g. live, staging'), )
def dump_db(site_name):
    """ Dumps remote db to local dev data folder for use with load_devdata"""
    dump_cmd = 'pg_dump -h {host} -U trapeze {project}_{site} > ../../devdata/dump.sql'
    local(dump_cmd.format(host=DB_HOST, project=PROJECT_NAME, site=site_name))
    print 'dumped ../../devdata/dump.sql'


@task
@args_required(('site_name', 'e.g. live, staging'), )
def dump_media(site_name):
    #aws.dump_bucket(
    """ Dumps s3 media files to local dev data folder for use with load_devdata"""
    dump_bucket(
        bucket_name=S3_BUCKETS[site_name],
        prefix='media/',
        out_path='../../devdata/files/',
        strip_prefix=True
    )


@task
@args_required(('site_name', 'e.g. live, staging'), )
def update_local_data(site_name):
    """ Runs both dump media and db commands """
    dump_db(site_name)
    dump_media(site_name)


###################################### END OF tasks that were in Fabfile.py


def _get_tag_from_commit(commit):
    """ Returns the tag of a commit """
    if commit.startswith('git-'):
        with hide('running', 'stdout', 'stderr'):
            result = local('git tag --points-at %s' % commit[4:20], capture=True)
        if result.succeeded:
            return '%s %s' % (colors.blue(result), commit[4:20])

    return commit


def _get_instance_environment(instance):
    """ Used in _sorted_instances and list_instances to get required instance tags """
    return instance.tags.get('elasticbeanstalk:environment-name', '')


def _sorted_instances(reservations):
    """ Returns instances that are passed in order by state"""
    instances = itertools.chain.from_iterable(res.instances for res in reservations)
    return sorted(instances, cmp=lambda a, b: cmp((_get_instance_environment(a), a.state), (_get_instance_environment(b), b.state)))


@task
def list_environments():
    """
    Prints a table of currently active AWS Elastic Beanstalk environments along with status information.
    """
    beanstalk = boto.beanstalk.connect_to_region(DEFAULT_REGION)
    environments = beanstalk.describe_environments()['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
    table = prettytable.PrettyTable(['Name', 'CNAME', 'Health/Status', 'Last Updated', 'Version'])
    table.align = 'l'
    print CLEAR_SCREEN
    print '\nREGION: %s' % DEFAULT_REGION
    for environment in environments:
        colorize = COLOR_FNS.get(environment['Health'], lambda s: s)

        table.add_row((
            environment['EnvironmentName'],
            colors.white(environment['CNAME']),
            colorize('%s/%s' % (environment['Health'], environment['Status'])),
            datetime.datetime.utcfromtimestamp(environment['DateUpdated']).strftime('%Y-%m-%d %H:%M:%S'),
            _get_tag_from_commit(environment['VersionLabel']),
         ))

    print table


@task
def list_instances(environment=None):
    """
    Prints a table of currently running EC2 instances along with status information.
    """
    ec2 = boto.ec2.connect_to_region(DEFAULT_REGION)
    reservations = ec2.get_all_instances()
    table = prettytable.PrettyTable(['ID', 'Host', 'IP', 'Type', 'State', 'Environment', 'Zone'])
    table.align = 'l'
    print CLEAR_SCREEN
    print '\nREGION: %s' % DEFAULT_REGION
    print 'EC2 INSTANCES'

    for instance in _sorted_instances(reservations):
        colorize = INSTANCE_STATE_FNS.get(instance.state, lambda s: s)
        table.add_row((
            instance.id,
            colors.white(instance.public_dns_name),
            instance.ip_address,
            instance.instance_type,
            colorize(instance.state),
            _get_instance_environment(instance),
            instance.placement,
        ))

    print table

    rds = boto.rds2.connect_to_region(DEFAULT_REGION)
    db_instances = rds.describe_db_instances()['DescribeDBInstancesResponse']['DescribeDBInstancesResult']['DBInstances']
    print '\nRDS INSTANCES'
    table = prettytable.PrettyTable(['ID', 'Host', 'Type', 'Status', 'Zones'])
    table.align = 'l'
    for instance in db_instances:
        colorize = colors.green if instance['DBInstanceStatus'] == 'available' else lambda s: s
        table.add_row((
            instance['DBInstanceIdentifier'],
            colors.white('%(Address)s:%(Port)s' % instance['Endpoint']),
            instance['DBInstanceClass'],
            colorize(instance['DBInstanceStatus']),
            '%s/%s' % (colors.white(instance['AvailabilityZone']), instance['SecondaryAvailabilityZone']),

        ))
    print table


@task
@args_required(
    ('site_name', 'e.g. live, staging'),
    ('tag', 'e.g. boulanger-0.0.1ALPHA, blank for develop'),
)
def deploy(site_name, tag=None):  # The environment must exist, as must the tag
    """
    Deploy a release to the specified AWS Elastic Beanstalk environment.
    """

    if not tag:
        tag = 'develop'  # use develop branch by default

    commit = local('git rev-parse %s^{commit}' % tag, capture=True)  # get commit id based on tag
    environment = '{0}-{1}'.format(PROJECT_NAME, site_name)  # project-env

    print colors.blue('deploying %s (%s) to %s on elasticbeanstalk') % (tag, commit[:8], environment)
    push_command = 'git aws.push -c %s --environment %s' % (commit, environment) # aws.push cmd created by eb init
    local(push_command)


@task
def dump_bucket(bucket_name, prefix='', out_path='', strip_prefix=False):
    """
    Download an S3 bucket.

    usage:

        fab dump_bucket:bucket_name[,prefix='prefix/'][,out_path='/path/'][,strip_prefix=True]

    args:

        bucket_name         - the name of the bucket *required*
        prefix              - bucket prefix (e.g. 'media/')
        out_path            - path to output downloaded files. Defaults to current directory. Must have trailing slash.
        strip_prefix        - strip the prefix from output filenames. Default False.

    """
    print 'dumping bucket', bucket_name
    if not isinstance(strip_prefix, bool):
        strip_prefix = (strip_prefix == 'True')

    try:
        s3 = boto.connect_s3()
        bucket = s3.get_bucket(bucket_name)
        for file in bucket.list(prefix=prefix):
            name = file.name
            if strip_prefix:
                name = re.sub(r'^%s' % prefix, '', name)

            outfile = os.path.abspath(os.path.join(out_path, name))
            outdir = os.path.dirname(outfile)
            if not os.path.exists(outdir):
                os.makedirs(outdir)
            if name and not name.endswith('/'):
                print outfile
                file.get_contents_to_filename(outfile)
    except boto.exception.S3ResponseError:
        print 'AWS returned Permission Denied. Is the time correct on your VM?'


def _filter_asg(site_name):
    def filt(group):
        tags = dict([(tag.key, tag.value) for tag in group.tags])
        environment = tags.get('elasticbeanstalk:environment-name', '')
        return environment == '{0}-{0}'.format(PROJECT_NAME, site_name)
    return filt


def _get_instances_for_site(site_name):
    conn = boto.ec2.autoscale.connect_to_region(DEFAULT_REGION)
    groups = filter(_filter_asg(site_name), conn.get_all_groups())
    instances = []
    for group in groups:
        instances.extend(instance.instance_id for instance in group.instances if instance.lifecycle_state == 'InService')

    instances.sort()

    ec2 = boto.ec2.connect_to_region(DEFAULT_REGION)
    return ec2.get_only_instances(instance_ids=instances)


@task
@args_required(('site_name', 'e.g. live, staging'), )
def leader(site_name):
    """ Returns ssh connection string to leader instance """
    instances = _get_instances_for_site(site_name)
    leader = instances[0].dns_name

    print 'setting user+host: ec2-user@%s' % leader
    env.user = 'ec2-user'
    env.hosts = [leader]


@task
@args_required(('site_name', 'e.g. live, staging'), )
def instances(site_name):
    """ Returns ssh connection string to available instance """
    instances = _get_instances_for_site(site_name)
    env.user = 'ec2-user'
    env.hosts = [instance.dns_name for instance in instances]
    print 'setting user+hosts: ec2-user@%s' % ','.join(env.hosts)

def _run_cmd_in_python_container(command):
    """ Used by manage, to enable the correct virtual env and app env to run a command"""
    source_venv = 'source /opt/python/run/venv/bin/activate'
    source_env = 'source /opt/python/current/env'
    run('{env} && {venv} && {cmd}'.format(env=source_env, venv=source_venv, cmd=command))


@task
def manage(command):
    """ Run a manage command remotely, need host that you can get from leader command. use appropriate cert """
    with cd('/opt/python/current/app/site/{0}/'.format(PROJECT_NAME)):
        _run_cmd_in_python_container('./manage.py %s' % command)


@task
@args_required(
    ('cmd', 'e.g. flush_all'),
)
def memcached(cmd):
    nc_cmd = 'nc `sed "s/:/ /g" <<< $CACHE_LOCATION` <<< "%s" ' % cmd
    cmd = 'if [ -z $CACHE_LOCATION ]; then echo "no memcached is used."; else echo $CACHE_LOCATION; %s; fi' % nc_cmd
    _run_cmd_in_python_container(cmd)
    print cmd

@task
def switch_credentials():
    """ Allow for quickly switching the account files for AWS api using eb and boto"""
    # TODO: fix
    # cp ~/.boto_PROJECT_NAME to ~/.boto
    # cp ~/.elasticbeanstalk/aws_credential_file ~/.elasticbeanstalk/aws_credential_file_PROJECT_NAME
    # if the file does not exist, ask user for input and create the files, then copy
    pass

@task
def generate_app_config():
    """ Generates .ebextensions/app.config file based on PROJECT_NAME"""
    import shutil
    import sys
    config_path = os.path.join(os.getcwd(), '../../.ebextensions/')
    config_file = os.path.join(config_path, '01_app.config')
    shutil.copy(os.path.join(config_path, '01_app.config.ex'), config_file)
    import fileinput

    searchExp = '{{project}}'
    for line in fileinput.input(file, inplace=True):
        if searchExp in line:
            line = line.replace(searchExp, PROJECT_NAME)
        sys.stdout.write(line)
