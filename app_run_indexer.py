import os
import json

from indexer.tasks import StableIndexerTasks


def options_from_config(filename=None):
    """ Options from file config.json """

    if not filename:
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.json')

    with open(filename) as f:
        options = json.load(f)

    return options


if __name__ == '__main__':

    config = options_from_config()

    if 'APP_MONGO_URI' in os.environ:
        config['mongo']['uri'] = os.environ['APP_MONGO_URI']

    if 'APP_MONGO_DB' in os.environ:
        config['mongo']['db'] = os.environ['APP_MONGO_DB']

    if 'APP_CONNECTION_URI' in os.environ:
        config['uri'] = os.environ['APP_CONNECTION_URI']

    indexer_tasks = StableIndexerTasks(config)
    indexer_tasks.start_loop()
