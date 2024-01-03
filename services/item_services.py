# from data.db_session import db_auth
import os
import pytz
# import pickle
from datetime import datetime
# import pandas as pd
import numpy as np
import uuid
import openai

from services.course_services import *
from services.utils import *
# from services.accounts_services import find_user
from data.db_connection import graph

from services.questions import *

from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(2)

cloud = os.getenv('CLOUD',False)
file_bucket = os.getenv('FILE_BUCKET','')


def fixVideoPath(url):
    # Remove suffix from end of url
    if '&' in url:
        url = url[:url.rfind('&')]

    if 'warpwire' in url:
        host = 'warpwire'
    elif 'youtube' in url:
        host = 'youtube'
        # In youtube link, replace watch with embed
        url = url.replace('watch?v=','embed/')
    elif 'youtu.be' in url:
        host = 'youtube'
        # In youtube link, replace watch with embed
        url = url.replace('youtu.be/','youtube.com/embed/')
    elif 'vimeo' in url:
        host = 'vimeo'
        # In vimeo link, replace watch with embed
        url = url.replace('vimeo.com/','player.vimeo.com/video/')
    elif 'zoom.us' in url:
        host = 'zoom'
    elif 'box.com' in url:
        host = 'box'
        url = url.replace('box.com/s/','app.box.com/embed/s/')
    else:
        host = ''

    return url,host

def getHost(url):
    if 'warpwire' in url:
        host = 'warpwire'
    elif 'youtube' in url:
        host = 'youtube'
    elif 'youtu.be' in url:
        host = 'youtube'
    elif 'vimeo' in url:
        host = 'vimeo'
    elif 'zoom.us' in url:
        host = 'zoom'
    elif 'box.com' in url:
        host = 'box'
    else:
        host = ''
    return host

class Item:
    def __init__(self,id):
        self.id = id
        self.name = None
        self.author = None
        self.type = None
        self.url = None
        self.docpath = None
        self.date_added = None
        self.description = None
        self.optional = None
        self.deadline = None
        self.timezone = None
        self.text = None
        self.repopath = None
        self.host = None

    def save_item(self,courseID,name,author,itemType,resourcepath,docpath,date_added,description,optional,deadline,text,repopath,host):
        self.name = name
        self.author = author
        self.type = itemType
        self.text = text
        self.resourcepath = resourcepath
        self.docpath = docpath
        self.date_added = date_added
        self.description = description
        self.optional = optional

        # set timezone and deadline if any
        if courseID is not None:
            classroom = Course(courseID)
            classroom.load_course()
            if hasattr(classroom,'timezone'):
                self.timezone = classroom['timezone']
            else:
                self.timezone = 'US/Eastern'
            deadline = convertDeadlineToUTC(deadline,self.timezone)
            self.deadline = deadline
        else:
            self.deadline = None
            self.timezone = None

        self.text = text
        self.repopath = repopath
        self.host = host

        # Fix video path
        if itemType == 'video' or itemType == 'lecture':
            url,host = fixVideoPath(resourcepath)
            self.resourcepath = url
            self.host = host

        # query to create item with properties
        query = """CREATE (x:item {id:$params['id'], name:$params['name'], author:$params['author'], type:$params['type'], resourcepath:$params['resourcepath'], docpath:$params['docpath'], date_added:$params['date_added'], description:$params['description'], optional:$params['optional'], deadline:$params['deadline'], timezone:$params['timezone'], text:$params['text'], repopath:$params['repopath'], host:$params['host']}) RETURN properties(x) as properties"""
        res = graph.createQuery(query,params=self.__dict__)

        # Add chunks
        if text != '':
            chunks = get_chunks(text,size=1000)
        else:
            chunks = []

        # Add chunks to graph
        for chunk in chunks:
            # chunkNode = Chunk()
            chunkNode = {}
            chunkNode['id'] = datetime.now().strftime('%Y%m-%d%H-%M%S-') + str(uuid.uuid4())
            chunkNode['text'] = chunk
            # Add embedding to chunkNode
            emb = embed(chunk)
            chunkNode['embedding'] = emb
            # query to add chunk to graph
            query = "CREATE (x:chunk {id:$params['id'], text:$params['text'], embedding:$params['embedding']}) RETURN properties(x) as properties"
            res = graph.createQuery(query,params=chunkNode)[0]

            # Add relationship to item
            query = '''MATCH (i:item),(c:chunk) WHERE i.id = '{}' AND c.id = '{}' CREATE (i)-[r:CHUNK_IN_ITEM]->(c) RETURN properties(r) as properties'''.format(self.id,chunkNode['id'])
            rel = graph.query(query)
        
        # Add relationship to course
        query = '''MATCH (c:classroom),(i:item) WHERE c.id = '{}' AND i.id = '{}' CREATE (c)-[r:HAS_ITEM]->(i) RETURN properties(r) as properties'''.format(courseID,self.id)

        return res
    
    def load_item(self):
        # query to get item with id self.id
        query = '''MATCH (x:item) WHERE x.id = "{}" RETURN properties(x) as properties'''.format(self.id)
        item = graph.query(query)[0]
        self.name = item['name']
        self.author = item['author']
        self.type = item['type']
        self.url = item['url']
        self.docpath = item['docpath']
        self.date_added = item['date_added']
        self.description = item['description']
        self.optional = item['optional']
        self.deadline = item['deadline']
        self.timezone = item['timezone']
        self.text = item['text']
        self.repopath = item['repopath']
        self.host = item['host']

        return self
    
    def delete_item(self):
        # delete chunks for item
        query = '''MATCH (i:item)-[:CHUNK_IN_ITEM]->(c:chunk) WHERE i.id = '{}' RETURN properties(c) as properties'''.format(self.id)
        chunks = graph.query(query)
        for chunk in chunks:
            # query to delete chunk
            query = '''MATCH (c:chunk) WHERE c.id = '{}' DETACH DELETE c'''.format(chunk['id'])
            graph.deleteQuery(query)

        # query to delete item with id self.id
        query = '''MATCH (x:item) WHERE x.id = "{}" DETACH DELETE x'''.format(self.id)
        res = graph.deleteQuery(query)
        return res

    def get_item_docpath(self):
        # query to get item with id self.id
        query = '''MATCH (x:item) WHERE x.id = "{}" RETURN properties(x) as properties'''.format(self.id)
        item = graph.query(query)[0]
        if (item['docpath'] != '') and (item['docpath'] is not None):
            if (cloud==True) or (cloud=="True"):
                path = get_signed_file_link(item['docpath'],file_bucket)
            else:
                path = item['docpath']
        else:
            path = ''
        return path
