# from data.db_session import db_auth
import os
from copy import copy
# import pickle
import uuid
from datetime import datetime
import random
import bisect
# import pandas as pd
import numpy as np
from flask import url_for

from data.db_connection import graph
from services.questions import *


cloud = os.getenv('CLOUD',False)
file_bucket = os.getenv('FILE_BUCKET','')

class Course:
    def __init__(self):
        self.id = None
        self.number = None
        self.name = None


    def save_course(self,usr,courseName,courseNum):
        self.id = str(uuid.uuid4())
        self.number = courseNum
        self.name = courseName
       
        # query to create a course and return properties of the course
        query = """CREATE (x:classroom {id:$params['id'],number:$params['number'],name:$params['name']}) RETURN properties(x) as properties"""
        course = graph.createQuery(query,params=self)[0]

        # Add link between user and course
        query = f"MATCH (x:user),(y:classroom) WHERE x.email='{usr}' AND y.id='{self.id}' CREATE (x)-[r:OWNS_CLASSROOM {{primaryOwner:'yes',createTime:'{str(datetime.utcnow().strftime('%m/%d/%Y'))}'}}]->(y) RETURN properties(r) as properties"
        rel = graph.query(query)[0]

        return course
    
    def load_course(self):
        # query to get course with id self.id
        query = f"MATCH (x:classroom) WHERE x.id='{self.id}' RETURN properties(x) as properties"
        course = graph.query(query)[0]
        self.number = course['number']
        self.name = course['name']
        return self
    
    def get_course_items(self):
        # query to get items with rel HAS_ITEM from course
        query = """MATCH (x:classroom)-[:HAS_ITEM]->(y:item) WHERE x.id = '{}' RETURN properties(y) as properties""".format(self.id)
        items = graph.query(query)
        return items
    
    def delete_course(self):
        # query to delete course with id self.id
        query = """MATCH (x:classroom) WHERE x.id = '{}' DETACH DELETE x""".format(self.id)
        graph.deleteQuery(query)
        return True
    

