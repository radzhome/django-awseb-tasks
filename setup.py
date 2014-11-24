from setuptools import setup, find_packages

setup(
    name='aws-fabric-tasks',
    packages=find_packages(exclude=['example']),
    install_requires=['prettytable', 'boto>=2.9.0', 'fabric>=1.5.0', ],
    include_package_data=True,
    version='0.0.1',
    description='AWS Fabric Tasks that wrap eb command line and use boto',
    long_description='TODO',
    author='Union Advertising',
    url='http://www.bitbucket.com/trapeze',
    license='BSD',
    zip_safe=False,
)
