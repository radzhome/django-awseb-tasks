from subprocess import call
from subprocess import check_call

import boto
import boto.beanstalk
from boto.beanstalk.exception import *
import time
import sys

import tempfile
import shutil
from elastic_beanstalk_config import *

# -*-python-*-

# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights
# Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy
# of the License is located at
#
#   http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the
# License.


class DevTools:
    def __init__(self):
        self.beanstalk_config = ElasticBeanstalkConfig(os.getcwd())
        self.eb = None
        self.s3 = None
        self.initialize_clients()

    def check_credentials_provided(self):
        if not self.beanstalk_config.access_key():
            sys.exit("The AWS Access Key ID was not provided. To add it, run \"git aws.config\"")

        if not self.beanstalk_config.secret_key():
            sys.exit("The AWS Secret Access Key was not provided. To add it, run \"git aws.config\"")

    def initialize_clients(self):
        self.check_credentials_provided()
        access_key = self.beanstalk_config.access_key()
        secret_key = self.beanstalk_config.secret_key()
        region = self.beanstalk_config.region()
        self.eb = boto.beanstalk.connect_to_region(region, aws_access_key_id=access_key,
                                                   aws_secret_access_key=secret_key)
        self.s3 = boto.s3.connect_to_region(region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)

    @staticmethod
    def commit_exists(commit):
        try:
            result = check_call(["git rev-parse", commit], shell=True)
            return result == 0
        except (CalledProcessError, OSError) as e:
            return False

    @staticmethod
    def git_object_type(commit):
        try:
            result = check_output("git cat-file -t {0}".format(commit), shell=True)
            if result:
                return result.strip()
        except (CalledProcessError, OSError) as e:
            return None

    @staticmethod
    def create_archive(commit, filename):
        print 'Creating git zip archive...'
        try:
            call("git archive {0} --format=zip > {1}".format(commit, filename), shell=True)
            print "git archive {0} --format=zip > {1}".format(commit, filename)
        except (CalledProcessError, OSError) as e:
            sys.exit("Error: Cannot archive your repository due to an unknown error")
        print 'Created zip archive.'

    def commit_id(self, commit):
        if not commit:
            commit = "HEAD"
        try:
            cmt_id = check_output("git rev-parse {0}".format(commit), shell=True)
            if cmt_id:
                cmt_id = cmt_id.strip()

            commit_type = self.git_object_type(commit)
            if "commit" != commit_type:
                sys.exit(
                    "{0} is a {1}. The value of the --commit option must refer to commit".format(commit, commit_type))

        except (CalledProcessError, OSError) as e:
            sys.exit("Error: Cannot find revision {0}".format(commit))

        return cmt_id

    @staticmethod
    def commit_message(commit):
        try:
            commit_message = check_output("git log -1 --pretty=format:%s {0}".format(commit), shell=True)
            if commit_message:
                return commit_message.strip()
        except (CalledProcessError, OSError) as e:
            return None

    def environment(self):
        try:
            current_branch = check_output("git rev-parse --abbrev-ref HEAD", shell=True)
            if current_branch:
                current_branch = current_branch.strip()
            if current_branch == "HEAD":
                return None
            branch_mappings = self.beanstalk_config.branch_mappings()
            if current_branch in branch_mappings:
                return branch_mappings[current_branch]
            return None
        except (CalledProcessError, OSError) as e:
            sys.exit("Error: Cannot lookup current branch")

    def version_label(self, commit, tag):

        if tag and '-' in tag:
            label = "{0}".format(tag)
        else:
            if tag:
                tag = '-' + tag
            epoch = int(time.time() * 1000)
            commit_id = self.commit_id(commit)
            label = "git-{0}-{1}_{2}".format(commit_id, epoch, tag)

        return label

    def bucket_name(self):
        print "Checking AWS S3 Application Version bucket."
        try:
            response = self.eb.create_storage_location()
        except TooManyBuckets:
            sys.exit("Error: You have exceeded the number of Amazon S3 buckets for your account")
        except InsufficientPrivileges:
            sys.exit(
                "Error: Access was denied to the Amazon S3 bucket. You must use AWS credentials that have permissions to access the bucket")
        except Exception:
            sys.exit("Error: Failed to get the Amazon S3 bucket name")

        if "CreateStorageLocationResponse" in response:
            if "CreateStorageLocationResult" in response["CreateStorageLocationResponse"]:
                if "S3Bucket" in response["CreateStorageLocationResponse"]["CreateStorageLocationResult"]:
                    return response["CreateStorageLocationResponse"]["CreateStorageLocationResult"]["S3Bucket"]
        sys.exit("Error: Failed to get the Amazon S3 bucket name")

    def upload_file(self, bucket_name, archived_file):
        name = os.path.basename(archived_file)
        self.initialize_clients()
        bkt = self.s3.get_bucket(bucket_name)
        print "Uploading git archive to S3 bucket '%s'..." % bucket_name
        key = boto.s3.key.Key(bkt, name)
        key.set_contents_from_filename(archived_file, cb=self.upload_progress_cb, num_cb=100)
        print "Upload done."

    @staticmethod
    def upload_progress_cb(so_far, total):
        print '- {} bytes transferred out of {} ({:.0f}%)...'.format(so_far, total, float(so_far)/total * 100)
        sys.stdout.write("\033[F")

    def update_environment(self, environment, version_label):
        print "Sending environment update signal..."
        try:
            self.eb.update_environment(environment_name=environment, version_label=version_label)
        except InsufficientPrivileges as e:
            sys.exit(
                "Error: Insufficient permissions to create the AWS Elastic Beanstalk application version. You must use AWS credentials that have the correct AWS Elastic Beanstalk permissions")
        except Exception as e:
            sys.exit("Error: Failed to update the AWS Elastic Beanstalk environment")
        print "Environment update initiated successfully. Wait for status to change from 'Updating' to 'Green'."

    def create_eb_application_version(self, commit_message, bucket_name, archived_file_name, version_label):
        print "Creating EB Application Version..."
        try:
            self.eb.create_application_version(self.beanstalk_config.application_name(), version_label,
                                               commit_message, bucket_name, archived_file_name)
            return version_label
        except TooManyApplications as e:
            sys.exit(
                "Error: You have exceeded the number of AWS Elastic Beanstalk applications for your account. For more information, see AWS Service Limits in the AWS General Reference")
        except TooManyApplicationVersions as e:
            sys.exit(
                "Error: You have exceeded the number of AWS Elastic Beanstalk application versions for your account. For more information, see AWS Service Limits in the AWS General Reference")
        except InsufficientPrivileges as e:
            sys.exit(
                "Error: Insufficient permissions to update the AWS Elastic Beanstalk environment. You must use AWS credentials that have the correct AWS Elastic Beanstalk permissions")
        except Exception as e:
            sys.exit("Error: Failed to create the AWS Elastic Beanstalk application version")
        print "Created EB Application Version."

    def create_application_version(self, env, commit, version_label=None):
        if not env:
            env = self.environment() or self.beanstalk_config.environment_name()
        if not commit:
            commit = "HEAD"

        if not version_label:
            version_label = self.version_label(commit)

        commit_message = self.commit_message(self.commit_id(commit))
        archived_file_path = tempfile.mkdtemp()
        archived_file_name = "{0}.zip".format(version_label)
        archived_file = os.path.join(archived_file_path, archived_file_name)
        self.create_archive(commit, archived_file)
        bucket_name = self.bucket_name()
        self.upload_file(bucket_name, archived_file)
        self.create_eb_application_version(commit_message, bucket_name, archived_file_name, version_label)
        shutil.rmtree(archived_file_path)

    def push_changes(self, env, commit, tag=None):
        if not env:
            env = self.environment() or self.beanstalk_config.environment_name()
        if not commit:
            commit = "HEAD"

        print "Preparing to update the AWS Elastic Beanstalk environment %s..." % env
        version_label = self.version_label(commit, tag=tag)
        self.create_application_version(env, commit, version_label)
        self.update_environment(env, version_label)
