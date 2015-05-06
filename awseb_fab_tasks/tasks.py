"""
Fabric tasks for interacting with AWS services using boto and eb tool, as well as prettytable for output.

"""
import datetime
import itertools
import os
import re
import sys
#import fileinput
import shutil
import time

import boto
import boto.beanstalk
import boto.ec2
import boto.ec2.autoscale
import boto.exception
import boto.rds2
from fabric import colors
from fabric.api import env, task, run, prompt, settings
from fabric.operations import local
from fabric.context_managers import hide, cd
import prettytable

from decorators import args_required


# Items set via FabFile, required for most of the stuff to work
DEFAULT_REGION = os.environ.get('DEFAULT_REGION', 'us-east-1')
PROJECT_NAME = os.environ.get('PROJECT_NAME')
DB_HOST = os.environ.get('DB_HOST')

# Used to copy templates and run extra scripts in eb_init and generate_config
EB_TASKS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))

# Pretty Table color settings
CLEAR_SCREEN = '\x1b[2J\x1b[H'
COLOR_FNS = {
    'Green': colors.green,
    'Grey': colors.yellow,  # Color Health states of env
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
EB_ENV_STATE_FNS = {
    'Ready': lambda s: colors.green(s, bold=True),
    'Updating': lambda s: colors.yellow(s, bold=True),
    'Launching': lambda s: colors.yellow(s, bold=True),
    'Terminating': lambda s: colors.yellow(s, bold=True),
}

#Defines the S3 Buckets based on the project name and the environment
#Problem, bucket names are unique, TODO: Make it something like projectteam-projectname-qa
S3_BUCKETS = {
    'staging': '%s-staging' % os.environ['PROJECT_NAME'],
    'live': '%s' % os.environ['PROJECT_NAME'],
    'qa': '%s-qa' % os.environ['PROJECT_NAME'],
    #'content': '%s-content' % os.environ['PROJECT_NAME'],  # used for testing
}


@task
@args_required(('site_name', 'e.g. live, staging', 'staging'),
               #('user_name', 'e.g. trapeze, projectteam'), # TODO: user change for new projects
               )
def dump_db(site_name):
    """ Dumps remote db to local dev data folder for use with load_devdata"""
    #dump_cmd = 'pg_dump -h {host} -U trapeze {project}_{site} > ../../devdata/dump.sql'
    dump_cmd = 'pg_dump -h {host} {project}_{site} > ../../devdata/dump.sql'
    local(dump_cmd.format(host=DB_HOST, project=PROJECT_NAME, site=site_name))
    print 'dumped ../../devdata/dump.sql'


@task
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
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
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
def update_local_data(site_name):
    """ Runs both dump media and db commands """
    dump_db(site_name)
    dump_media(site_name)


@task
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
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
        #TODO: need to create media & static directories? test
    except boto.exception.S3CreateError:
        print 'AWS returned 409 Conflict. Does the bucket already exist?'



#TODO: Copy bucket?, rm bucket conn.delete_bucket()
@task
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
def media_to_bucket():
    """ Send local media to the env bucket """
    pass
    #TODO


def _get_tag_from_commit(commit):
    """ Returns the tag of a commit """  # TODO: Try and get rid of dependency on points-at
    if commit and commit.startswith('git-'):
        last = commit.rfind("-")
        with hide('running', 'stdout', 'stderr'), settings(warn_only=True):

            result = local('git tag --points-at %s' % commit[4:last], capture=True)
            # if result.stderr:
            #     result = local('git tag --points-at %s' % commit[4:20], capture=True)
            if result.stderr:
                return commit
        # if result.succeeded:
        #     return '%s %s' % (colors.blue(result), commit[4:20])
    return commit


def _get_instance_environment(instance):
    """ Used in _sorted_instances and list_instances to get required instance tags """
    return instance.tags.get('elasticbeanstalk:environment-name', '')


def _sorted_instances(reservations):
    """ Returns instances that are passed in order by state"""
    instances = itertools.chain.from_iterable(res.instances for res in reservations)
    return sorted(instances, cmp=lambda a, b: cmp((_get_instance_environment(a), a.state), (_get_instance_environment(b), b.state)))


def _get_environment_status(environment_name):
    """ Gets the environment status. """
    beanstalk = boto.beanstalk.connect_to_region(DEFAULT_REGION)
    environment = beanstalk.describe_environments(
        environment_names=[environment_name, ]
    )['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
    return environment[0]['Status'], environment[0]['Health']

@task
@args_required(
    ('environment_name', 'e.g. {0}-staging'.format(PROJECT_NAME), '{0}-staging'.format(PROJECT_NAME)),
)
def environment_status(environment_name):
    """ Gets the environment status. """
    environment = _get_environment_status(environment_name)
    print "Details for {}".format(environment_name)
    colorize = COLOR_FNS.get(environment[1], lambda s: s)
    print 'Status:', colorize(environment[0]), ' Health:', colorize(environment[1])


@task
def list_environments():
    """ Prints a table of currently active AWS Elastic Beanstalk environments along with status information. """
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
            _get_tag_from_commit(environment['VersionLabel']), ))
    print table


@task
def status():
    return list_environments()


@task
def list_instances():
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
    ('site_name', 'e.g. live, staging', 'staging'),
    ('version_label', 'See status command for available versions', ),
)
def update(site_name, version_label=None):
    from eb_devtools.scripts.aws.dev_tools import DevTools
    dev_tools = DevTools()
    environment = '{0}-{1}'.format(PROJECT_NAME, site_name)
    dev_tools.update_environment(environment, version_label)


@task
@args_required(
    ('site_name', 'e.g. live, staging', 'staging'),
    ('tag', 'e.g. {0}-0.0.1ALPHA'.format(PROJECT_NAME), 'develop'),
)
def deploy(site_name, tag=None):  # The environment must exist, as must the tag
    """
    Deploy a release to the specified AWS Elastic Beanstalk environment.
    """

    environment = '{0}-{1}'.format(PROJECT_NAME, site_name)  # project-site

    # Will raise an error if can't connect to environment
    beanstalk = boto.beanstalk.connect_to_region(DEFAULT_REGION)
    beanstalk.describe_environment_resources(environment_name=environment)

    print "Running 'git pull'..."
    with hide('running'):
        local('git pull')  # pull to ensure tag is there
        commit = local('git rev-parse %s^{commit}' % tag, capture=True)  # get commit id based on tag

    # Check if version exists already
    from eb_devtools.scripts.aws.dev_tools import DevTools
    dev_tools = DevTools()
    version_label = dev_tools.version_label(commit, tag)  # commit, tag

    version_label_exists = beanstalk.describe_application_versions(version_labels=[version_label, ],)['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult']['ApplicationVersions']
    if not version_label_exists:
        with hide('running'):
            commit_tag = local('git tag --contains %s' % commit, capture=True)  # Get the tag of the commit if exists
        commit_tag = commit_tag.strip('\n')
        if commit_tag: commit_tag = commit_tag.split('\n')
        if len(commit_tag) == 1:
            version_label_exists = beanstalk.describe_application_versions(version_labels=[commit_tag[0], ],)['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult']['ApplicationVersions']
            version_label = commit_tag[0]
    deploy_existing = 'n'
    if version_label_exists:
        deploy_existing = prompt("Version label {} already exists in 'Application Versions'. Deploy it? (Y/N) "
                                 "[default: Y]".format(version_label))
        if deploy_existing.lower() != 'n':
            print "Updating environment {} exiting version label {}".format(environment, version_label)
            dev_tools.update_environment(environment, version_label)
    
    if deploy_existing.lower() == 'n':
        print colors.blue('Deploying %s (%s) to %s to Elastic Beanstalk...') % (tag, commit[:8], environment)
        with hide('running'):
            push_command = 'git aws.push -c {0} --environment {1} --tag {2}'.format(commit, environment, tag)
        local(push_command)

    poll_env = prompt("Poll environment status until 'Ready' state? (Y/N) [default: Y]")
    if poll_env.lower() != 'n':
        dot_print = '.'
        while True:
            time.sleep(5)
            status, health = _get_environment_status(environment)
            sys.stdout.write("Status & Health: {}, {}{}\r".format(status, health, dot_print))
            sys.stdout.flush()
            dot_print += "."
            if status == 'Ready':
                print '\n'
                colorize = COLOR_FNS.get(health, lambda s: s)
                colorize('Environment Ready, and status {}.'.format(health))
                break
        print "Environment update complete. See AWS Beanstalk console for details."

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
    print 'Dumping bucket', bucket_name
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
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
def leader(site_name):
    """ Returns ssh connection string to leader instance """
    insts = _get_instances_for_site(site_name)
    leader = insts[0].dns_name
    env.user = 'ec2-user'
    print 'setting user+host: %s@%s' % (env.user, leader)
    env.hosts = [leader]

@task
@args_required(('site_name', 'e.g. live, staging', 'staging'), )
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
    
    # TODO: make manage also run manage.py --fake-initial  (south error: no such option: --fake-initial)
    with cd('/opt/python/current/app/site/{0}/'.format(PROJECT_NAME)):
        _run_cmd_in_python_container('./manage.py %s' % command)


@task
@args_required(
    ('cmd', 'e.g. flush_all'),
)
def memcached(cmd):
    """ TODO """
    nc_cmd = 'nc `sed "s/:/ /g" <<< $CACHE_LOCATION` <<< "%s" ' % cmd
    cmd = 'if [ -z $CACHE_LOCATION ]; then echo "no memcached is used."; else echo $CACHE_LOCATION; %s; fi' % nc_cmd
    _run_cmd_in_python_container(cmd)
    print cmd


def _get_project_boto_creds():
    return os.path.join(os.path.expanduser("~"), '{0}_{1}'.format('.boto', PROJECT_NAME))


def _get_master_boto_creds():
    return os.path.join(os.path.expanduser("~"), '.boto',)


def _copy_if_no_exists(project_boto_creds, master_boto_creds):
    """
    Copy the file if it isn't already there
    """
    if not os.path.exists(master_boto_creds):
        shutil.copy(project_boto_creds, master_boto_creds)
    os.chmod(project_boto_creds, 0600)

@task
def new_creds():
    """ Create new credentials, overwrite if required. Switched to the new credentials."""
    # Check if creds exist, ask if overwrite if they do
    project_boto_creds = _get_project_boto_creds()
    master_boto_creds = _get_master_boto_creds()
    if os.path.exists(project_boto_creds):
        overwrite = prompt('Credentials file already exists for {}. Overwrite it (Y/N)? [default: N]: '.format(
            PROJECT_NAME))
        if overwrite.lower() == 'y':
            os.remove(project_boto_creds)
        else:
            return _copy_if_no_exists(project_boto_creds, master_boto_creds)

    with open(os.path.join(EB_TASKS_BASE_PATH, 'eb_devtools', 'scripts', 'aws.credentials_format.txt')) as f:
        credential_format = f.read().replace('<', '{').replace('>', '}')

    aws_access_key = prompt('Please provide the AWS_ACCESS_KEY for {}: '.format(PROJECT_NAME))
    aws_secret_key = prompt('Please provide the AWS_SECRET_KEY for {}: '.format(PROJECT_NAME))

    new_credentials_string = credential_format.format(
        YOUR_AWS_ACCESS_KEY_ID=aws_access_key,
        YOUR_AWS_SECRET_ACCESS_KEY=aws_secret_key,
    )

    with open(project_boto_creds, 'w') as f:
        f.write(new_credentials_string)
    os.chmod(project_boto_creds, 0600)
    _copy_if_no_exists(project_boto_creds, master_boto_creds)

    print "Credentials file created."

    # Automatically switch to the credentials for this project
    sw_creds()

@task
def sw_creds():
    """
    Allow for quickly switching the account files for AWS api using eb tasks and boto.
    Required because boto always looks for .boto and might not be correct based on curent project.
    """
    home_dir = os.path.expanduser("~")
    master_boto_file = '.boto'
    master_boto_creds = _get_master_boto_creds()
    project_boto_creds = _get_project_boto_creds()

    if os.path.exists(project_boto_creds) and os.path.isfile(project_boto_creds):  # files exist
        import filecmp
        if filecmp.cmp(master_boto_creds, project_boto_creds):  # correct file is currently set
            print "Correct credentials already set for {}.".format(PROJECT_NAME)
        else:
            shutil.copy(project_boto_creds, master_boto_creds)
            #Set permissions if needed here
            print "Set {0} credentails as default".format(PROJECT_NAME)
    else:

        if os.path.exists(master_boto_creds) and os.path.isfile(master_boto_creds):
            master_proj = prompt('What project are the current files for? (Blank for {0}): '.format(PROJECT_NAME))
            if master_proj:
                project_boto_creds = os.path.join(home_dir, '{0}_{1}'.format(master_boto_file, master_proj))
            shutil.copy(master_boto_creds, project_boto_creds)
            os.chmod(project_boto_creds, 0600)
            if master_proj and master_proj != PROJECT_NAME:
                print "Credentails set for {0}, not found for {1}.".format(master_proj, PROJECT_NAME)
        else:
            print "No master files found in your home directory."
        print "Create current project files in {0} is in correct format in your home directory " \
              "and try this command again to save the file.".format(master_boto_file)
        return
    print "Set credential files done"


def _get_git_root_dir():
    """
    Returns the root of the git repository
    """
    with hide('running', 'stdout', 'stderr'):
        return local('git rev-parse --show-toplevel', capture=True)  # get stderr & stdout


def _get_ebextensions_dir():
    """
    Returns the .ebextensions directory which is always at the root of the repository
    """
    with hide('running', 'stdout', 'stderr'):
        git_directory = _get_git_root_dir()
    return os.path.join(git_directory, '.ebextensions/')

@task
def generate_app_config():  # generate_ebxconfig():
    """ Generates .ebextensions/app.config file based on PROJECT_NAME"""

    print "Creating ebextensions..."

    # Configure needed directories
    config_path = _get_ebextensions_dir()
    config_ex_path = os.path.join(EB_TASKS_BASE_PATH, 'eb_devtools/ebextensions/')

    if not os.path.exists(config_path):
        os.mkdir(config_path)

    is_postgis = prompt('Does {} require postgis support (Y/N)? [default: Y]: '.format(
        PROJECT_NAME))
    if is_postgis.lower().strip() == 'n':
        db_backend_string = 'postgres'
    else:
        db_backend_string = 'postgis'

    # Copy ebextension 01 ex to .ebextensions & replace project name
    config_ex_file1 = os.path.join(config_ex_path, '01_app_%s.config.ex' % db_backend_string)
    config_file1 = os.path.join(config_path, '01_%s_%s.config' % (PROJECT_NAME, db_backend_string))
    with open(config_ex_file1, 'r') as f:
        config_file1_buf = f.read()
    config_file1_buf = config_file1_buf.format(project=PROJECT_NAME)
    with open(config_file1, 'w') as f:
        f.write(config_file1_buf)

    # Copy ebextension 00 ex to .ebextensions
    config_file0 = os.path.join(config_path, '00_repo_%s.config' % db_backend_string)
    shutil.copy(os.path.join(config_ex_path, '00_repos_%s.config.ex' % db_backend_string), config_file0)


def _line_prepend_to_file(filename, line):
    """ Adds a line to the top of a file """
    with open(filename, 'r+') as f:
        content = f.read()
        f.seek(0, 0)
        f.write(line.rstrip('\r\n') + '\n' + content)


@task
def eb_init():  # The environment must exist, as must the tag
    """
    Initiate eb tools copy to .git of repo
    """

    #TODO: Copy the required files needed for beanstalk wsgi settings
    import boto  # Try to import to verify installation
    boto_path = boto.__path__[0][:boto.__path__[0].rfind('/')]
    boto_path_import = "import sys; sys.path.insert(0, '{}')".format(boto_path) # Fail if boto found in wrong path
    new_creds()
    if not os.path.exists(_get_ebextensions_dir()):
        generate_app_config()
    else:
        print "Skipping .ebextensions/ creation, .ebextensions already exists..."
    sh_path = os.path.join(EB_TASKS_BASE_PATH, 'eb_devtools/AWSDevTools-RepositorySetup.sh')
    with hide('running', 'stdout', 'stderr'):
        local('bash ' + sh_path)  # Run shell script that creates git aliases
    dev_tools_path = os.path.join(_get_git_root_dir(), '.git', 'AWSDevTools', 'aws', 'dev_tools.py')
    _line_prepend_to_file(dev_tools_path, boto_path_import)
    print "Pre appended dev_tools with path to projects lib dir"
    print "Running 'git aws.config'..."
    with hide('running'):
        local('git aws.config')  # No need for now, asks for key again


#TODO:
def eb_restart():
    #beanstalk.restart_app_server(environment_id=None, environment_name=None)
    pass

#TODO
def eb_rebuild():
    # beanstalk.rebuild_environment(environment_id=None, environment_name=None)
    pass

#TODO:
def eb_swap_cnames():
    #beanstalk.swap_environment_cnames(source_environment_id=None, source_environment_name=None, destination_environment_id=None, destination_environment_name=None)
    pass

#TODO:
def eb_logs():
    # See AWS EB tools how it does it, use it.
    pass

# TODO: list_available_solution_stacks()

# TODO: research validate_configuration_settings  / rquest n retrieve environment info

# TODO: move directories around so easier to import modules

# TODO: App config should generate settings_prod.py & replace wsgi.py as well for beanstalk

# TODO: Eb logs ( would be cool)

# TODO: Eb restart / update env

# TODO: Eb load /save / export env settings i.e. env vars etc..
