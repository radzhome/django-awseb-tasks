from setuptools import setup, find_packages

setup(
    name='awseb-fab-tasks',
    packages=find_packages(exclude=['example']),
    install_requires=['prettytable', 'boto>=2.9.0', 'fabric>=1.5.0', ],  # fab should be globally installed
    extras_require={
        's3_backend':  ["django-storages==1.1.8", ],  # django-storages is OPTIONAL
    },
    include_package_data=True,
    version='0.0.1',
    description='AWS Elastic Beanstalk Fabric Tasks that use boto',
    long_description='TODO',
    author='radlws',
    url='http://www.github.com/radlws',
    license='BSD',
    zip_safe=False,
)
