import logging
import json

# pip packages
import boto3

class Aws:
    def detect_labels_local_file(self, fileName):
        if not self.client:
            self.client = boto3.client('rekognition')
       
        with open(fileName, 'rb') as image:
            response = self.client.detect_labels(Image={'Bytes': image.read()})

        logging.debug('Response: ' + json.dumps(response))

        return response.get('Labels', '')
    
    def __init__(self):
        self.client = None