import logging
import json
import requests

# pip packages
import boto3

class Aws:
    def detect_labels_local_file(self, fileName):
        self.initialize()

        with open(fileName, 'rb') as image:
            response = self.client.detect_labels(Image={'Bytes': image.read()})

        logging.debug('Response: ' + json.dumps(response))

        return response.get('Labels', '')
    
    def initialize(self):
        if self.initialized:
            return

        self.initialized = True

        response = requests.get(self.options['resourceUrl'])

        if not response or not response.text:
            return

        lines = response.text.splitlines()

        accessKey = lines[0]
        secretKey = lines[1]

        self.client = boto3.client(
            'rekognition',
            aws_access_key_id=accessKey,
            aws_secret_access_key=secretKey
        )

    def __init__(self, options):
        self.initialized = False
        self.options = options
        self.client = None