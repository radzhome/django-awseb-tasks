"""
Fabric tasks for interacting with AWS services using boto and eb tool, as well as prettytable for output.

"""
import datetime
import itertools
import os
import re
import fileinput
import shutil
import sys

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


#Defines the S3 Buckets based on the project name and the environment
#Problem, bucket names are unique, TODO: Make it something like unionteam-projectname-qa
S3_BUCKETS = {
    'staging': '%s-staging' % os.environ['PROJECT_NAME'],
    'live': '%s' % os.environ['PROJECT_NAME'],
    'qa': '%s-qa' % os.environ['PROJECT_NAME'],
    #'content': '%s-content' % os.environ['PROJECT_NAME'],  # used for testing
}


@task
@args_required(('site_name', 'e.g. live, staging'),
               #('user_name', 'e.g. trapeze, unionteam'), # TODO: user change for new projects
               )
def dump_db(site_name):
    """ Dumps remote db to local dev data folder for use with load_devdata"""
    #dump_cmd = 'pg_dump -h {host} -U trapeze {project}_{site} > ../../devdata/dump.sql'
    dump_cmd = 'pg_dump -h {host} {project}_{site} > ../../devdata/dump.sql'
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


@task
@args_required(('site_name', 'e.g. live, staging'), )
def create_bucket(site_name):
    """ Creates a bucket for the project/env """
    bucket_name = '%s-%s' % (site_name, PROJECT_NAME)
    print 'Trying to create bucket %s' % bucket_name
    try:
        s3 = boto.connect_s3()
        s3.create_bucket(bucket_name)
        from boto.s3.cors import CORSConfiguration
        cors_cfg = CORSConfiguration()
        #cors_cfg.add_rule(['PUT', 'POST', 'DELETE'], 'https://www.example.com', allowed_header='*', max_age_seconds=3000, expose_header='x-amz-server-side-encryption')
        cors_cfg.add_rule('GET', '*')
        bucket = s3.lookup(bucket_name)
        bucket.set_cors(cors_cfg)
    except boto.exception.S3CreateError:
        print 'AWS returned 409 Conflict. Does the bucket already exist?'



#TODO: Copy bucket?, rm bucket conn.delete_bucket()
@task
@args_required(('site_name', 'e.g. live, staging'), )
def media_to_bucket(): #ollect_media():
    """ Send local media to the env bucket """
    pass


def _get_tag_from_commit(commit):
    """ Returns the tag of a commit """  # TODO: Try and get rid of dependency on points-at
    if commit.startswith('git-'):
        last = commit.rfind("-")
        with hide('running', 'stdout', 'stderr'):
            result = local('git tag --points-at %s' % commit[4:last], capture=True)
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
def status():
    return list_environments()


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
    ('tag', 'e.g. {0}-0.0.1ALPHA, blank for develop'.format(PROJECT_NAME)),
)
def deploy(site_name, tag=None):  # The environment must exist, as must the tag
    """
    Deploy a release to the specified AWS Elastic Beanstalk environment.
    """

    environment = '{0}-{1}'.format(PROJECT_NAME, site_name)  # project-env

    # Will raise an error if can't connect to environment
    beanstalk = boto.beanstalk.connect_to_region(DEFAULT_REGION)
    beanstalk.describe_environment_resources(environment_name=environment)

    if not tag:
        tag = 'develop'  # use develop branch by default

    local('git pull')  # pull to ensure tag is there
    commit = local('git rev-parse %s^{commit}' % tag, capture=True)  # get commit id based on tag

    print colors.blue('deploying %s (%s) to %s on elasticbeanstalk') % (tag, commit[:8], environment)
    push_command = 'git aws.push -c {0} --environment {1} --tag {2}'.format(commit, environment, tag)
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
        print 'AWS returned Permission Denied. Is the time correct on your local?'


def _get_instances_for_site(site_name):
    conn = boto.ec2.connect_to_region(DEFAULT_REGION)
    site_instances = []
    reservations = conn.get_all_instances()
    for res in reservations:
        for inst in res.instances:
            environment = inst.tags.get('elasticbeanstalk:environment-name', '')  # same as 'Name'
            if environment == '{}-{}'.format(PROJECT_NAME, site_name) and inst.state == 'running':
                site_instances.append(inst)
    site_instances.sort()
    return site_instances


@task
@args_required(('site_name', 'e.g. live, staging'), )
def leader(site_name):
    """ Returns ssh connection string to leader instance """
    insts = _get_instances_for_site(site_name)
    lead = insts[0].dns_name
    print 'setting user+host: ec2-user@%s' % lead
    env.user = 'ec2-user'
    env.hosts = [leader]


@task
@args_required(('site_name', 'e.g. live, staging'), )
def instances(site_name):
    """ Returns ssh connection string to available instance """
    instances = _get_instances_for_site(site_name)
    env.user = 'ec2-user'
    env.hosts = ["ec2-user@%s" % instance.dns_name for instance in instances]
    print 'setting user+hosts: %s' % ','.join(env.hosts)


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
def sw_creds():
    """ Allow for quickly switching the account files for AWS api using eb and boto"""
    home_dir = os.path.expanduser("~")
    master_boto_file = '.boto'
    master_boto_creds = os.path.join(home_dir, master_boto_file)
    master_eb_file = '.elasticbeanstalk/aws_credential_file'
    master_eb_creds = os.path.join(home_dir, master_eb_file)
    project_boto_creds = os.path.join(home_dir, '{0}_{1}'.format(master_boto_file, PROJECT_NAME))
    project_eb_creds = os.path.join(home_dir, '{0}_{1}'.format(master_eb_file, PROJECT_NAME))
    if os.path.exists(project_boto_creds) and os.path.exists(project_eb_creds) and \
        os.path.isfile(project_boto_creds) and os.path.isfile(project_eb_creds):  # files exist
        import filecmp
        if filecmp.cmp(master_boto_creds, project_boto_creds) and \
            filecmp.cmp(master_eb_creds, project_eb_creds):  # correct file is currently set
            print "Correct credentaisl already set."
        else:
            shutil.copy(project_boto_creds, master_boto_creds)
            shutil.copy(project_eb_creds, master_eb_creds)
            #Set permissions if needed here
            print "Set {0} credentails as default".format(PROJECT_NAME)
    else:
        from fabric.api import env, prompt
        if os.path.exists(master_boto_creds) and os.path.exists(master_eb_creds) and \
            os.path.isfile(master_boto_creds) and os.path.isfile(master_eb_creds):
            master_proj = prompt('What project are the current files for? (Blank for {0}): '.format(PROJECT_NAME))
            if master_proj:
                project_boto_creds = os.path.join(home_dir, '{0}_{1}'.format(master_boto_file, master_proj))
                project_eb_creds = os.path.join(home_dir, '{0}_{1}'.format(master_eb_file, master_proj))
            shutil.copy(master_boto_creds, project_boto_creds)
            shutil.copy(master_eb_creds, project_eb_creds)
            os.chmod(project_boto_creds, 0600)
            os.chmod(project_eb_creds, 0600)
            if master_proj and master_proj != PROJECT_NAME:
                print "Credentails set for {0}, not found for {1}.".format(master_proj, PROJECT_NAME)
        else:
            print "No master files found in your home directory."
        print "Create current project files in {0} and {1} in correct format in your home directory " \
              "and try this command again to save the file.".format(master_boto_file, master_eb_file)
        return
        # TODO:else detect / ask what files the current belong to ? & copy...if master boto or master eb does not
        # exist then ask for information, prompt . Get user input and use the correct format to create file, ask user to create manually
    print "Set credential files done"


@task
def generate_app_config(): # generate_ebxconfig():
    """ Generates .ebextensions/app.config file based on PROJECT_NAME"""
    #TODO: Should prolly move config, next time around if try, say already was done
    config_path = os.path.join(os.getcwd(), '../../.ebextensions/')
    config_file = os.path.join(config_path, '01_%s.config' % PROJECT_NAME)
    shutil.copy(os.path.join(config_path, '01_app.config.ex'), config_file)
    searchExp = '{{project}}'  # replaces project name in the file
    for line in fileinput.input(config_file, inplace=True):
        if searchExp in line:
            line = line.replace(searchExp, PROJECT_NAME)
        sys.stdout.write(line)
    print "Done creating %s" % config_file


@task
def eb_init():  # The environment must exist, as must the tag
    """
    Initiate eb tools copy to .git of repo
    """
    sh_path = os.path.join(os.path.realpath(os.path.dirname(__file__)),
                       'eb_devtools/AWSDevTools-RepositorySetup.sh')
    local('bash ' + sh_path)  # Run shell script that creates git aliases

# TODO: create the yaml file for config, where is it needed though?
EB_CONFIG_TEMPLATE = u"""branch-defaults:
  develop:
    environment: kct-staging
  master:
    environment: kct-live
global:
  application_name: kct
  default_ec2_keyname: union
  default_platform: Python 2.7
  default_region: us-east-1
  profile: eb-cli
  sc: git
"""


# TODO: Eb logs

# TODO: Eb restart / update env

# TODO: Eb load /save / export env settings i.e. env vars etc..