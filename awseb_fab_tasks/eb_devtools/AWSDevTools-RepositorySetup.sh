echo "Creating EB aws.push & aws.config extensions for git..."
SCRIPT_DIR="$( cd "$( dirname "$0" )" && pwd )"
GIT_DIRECTORY="$(git rev-parse --show-toplevel)/.git"

if [ -z "$GIT_DIRECTORY" ]; then GIT_DIRECTORY=.git; fi

rm -rf $GIT_DIRECTORY/AWSDevTools
cp -r "$SCRIPT_DIR"/scripts $GIT_DIRECTORY/AWSDevTools

git config alias.aws.elasticbeanstalk.remote "!$GIT_DIRECTORY/AWSDevTools/aws.elasticbeanstalk.push --remote-url"
git config aws.endpoint.us-east-1 git.elasticbeanstalk.us-east-1.amazonaws.com
git config aws.endpoint.ap-northeast-1 git.elasticbeanstalk.ap-northeast-1.amazonaws.com
git config aws.endpoint.eu-west-1 git.elasticbeanstalk.eu-west-1.amazonaws.com
git config aws.endpoint.us-west-1 git.elasticbeanstalk.us-west-1.amazonaws.com
git config aws.endpoint.us-west-2 git.elasticbeanstalk.us-west-2.amazonaws.com
git config aws.endpoint.ap-southeast-1 git.elasticbeanstalk.ap-southeast-1.amazonaws.com
git config aws.endpoint.ap-southeast-2 git.elasticbeanstalk.ap-southeast-2.amazonaws.com
git config aws.endpoint.sa-east-1 git.elasticbeanstalk.sa-east-1.amazonaws.com
git config alias.aws.elasticbeanstalk.push "!$GIT_DIRECTORY/AWSDevTools/aws.elasticbeanstalk.push"
git config alias.aws.push '!git aws.elasticbeanstalk.push'
git config alias.aws.elasticbeanstalk.config "!$GIT_DIRECTORY/AWSDevTools/aws.elasticbeanstalk.config"
git config alias.aws.config '!git aws.elasticbeanstalk.config'
git config alias.aws.elasticbeanstalk.createapplicationversion "!$GIT_DIRECTORY/AWSDevTools/aws.elasticbeanstalk.createapplicationversion"
git config alias.aws.createapplicationversion '!git aws.elasticbeanstalk.createapplicationversion'

