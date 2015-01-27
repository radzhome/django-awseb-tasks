TODO
-----
- sep. poll_env so can use it on other commands and sep.
- combine collect static / migrate commands with deploy
- logging (retrieve /var/log/* using fabric), ability to tail logs (see eb cli tool)
- template creation from config file / setup create new app / env based on options
- eb logs - re-create from eb cli and add
- eb init to generate custom templates for settings / wsgi py files
- download some logs: https://www.digitalocean.com/community/tutorials/how-to-use-fabric-to-automate-administration-tasks-and-deployments
- Docker
- cleanup memcached to be sep (Ask if memcached is required. These are the libs:
- 
    libmemcached: ''
    libmemcached-devel: ''
    cyrus-sasl-devel: ''
    zlib-devel: ''

- add check last error
boto: describe_events, see also create_configuration_template
```
                events = eb_client.describe_events(app_name,
                                                   env_name,
                                                   max_records=ServiceDefault.STATUS_EVENT_MAX_NUM,
                                                   severity=ServiceDefault.STATUS_EVENT_LEVEL)
                if len(events.result) > 0:
                    # Having one error event
                    for event in events.result:
                        msg = u'{0}\t{1}\t{2}'.format(event.event_date,
                                                      event.severity,
                                                      event.message)
                        log.info(u'Found last error event: {0}'.format(msg))
                        prompt.plain(msg)
```

Feature Request
------------------
* Add ability to copy buckets
* Add ability to send local media files to bucket
* Log history / descibe events:
* beanstalk.describe_events(application_name='kpmkhv', environment_name='kpmkhv-staging', max_records=100)
* 
