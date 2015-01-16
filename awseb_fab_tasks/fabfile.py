from fabric.api import env
import os

os.environ['PROJECT_NAME'] = 'testproj'
#os.environ['PROJECT_NAME'] = os.getcwd().split('/')[-1]  # Import before aws_tasks, as it is used there.
os.environ['DEFAULT_REGION'] = 'us-east-1'
if 'project_name' not in env:
    env.project_name = os.environ.get('PROJECT_NAME', '')
    if env.project_name:
        env.user = env.project_name + 'team'

import tasks as aws