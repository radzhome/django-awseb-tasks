from urlparse import urljoin

from django.conf import settings
from storages.backends.s3boto import S3BotoStorage


# Overridden location property allows us to keep media and static files
# in separate subfolders on S3
class StaticS3Storage(S3BotoStorage):
    location = 'static'

    def modified_time(self, path):
        # XXX
        # Force collectstatic to not check times
        # We were having issues with files not collecting due to timestamps
        # being weird (the backend was thinking the local files were out of date
        # compared to the stale ones on S3)
        raise NotImplementedError


class MediaS3Storage(S3BotoStorage):
    location = 'media'

    def url(self, name):
        # The default S3BotoStorage url is to generate an S3 signed url
        # The query params from the signed url screw up the ajax uploader
        # and we dont really need them anyway, so just joining the media url
        # with the name here is sufficient.
        return urljoin(settings.MEDIA_URL, name)
