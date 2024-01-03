# from data.db_session import db_auth
import os
import uuid
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer
from typing import Optional
from passlib.handlers.sha2_crypt import sha512_crypt as crypto

from data.db_connection import graph


cloud = os.getenv('CLOUD',False)
secret_key = os.getenv('SECRET_KEY','')
salt = os.getenv('SECURITY_PASSWORD_SALT','')

def hash_text(text: str) -> str:
    hashed_text = crypto.encrypt(text)
    return hashed_text


def verify_hash(hashed_text: str, plain_text: str) -> bool:
    return crypto.verify(plain_text, hashed_text)

def confirm_token(token, expiration=3600*24):
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        email = serializer.loads(
            token,
            salt=salt,
            max_age=expiration
        )
    except:
        return False
    return email


class User:
    def __init__(self,usr):
        self.usr = usr
        self.name = None
        self.lastname = None
        self.wholename = None
        self.initials = None
        self.email = usr
        self.hashed_password = None
        self.account_type = None
        self.plan = None

    def save_user(self,firstname,lastname,password,status,plan):
        self.name = firstname
        self.lastname = lastname
        self.wholename = firstname + ' ' + lastname
        self.initials = firstname[0] + lastname[0]
        self.hashed_password = hash_text(password)
        self.account_type = status
        self.plan = plan
        self.paid = 'no'
        self.created_on = str(datetime.now().strftime('%m/%d/%Y'))
        self.confirmed = False
        if not cloud:
            self.confirmed = True
   
        # query to create user with properties
        query = """CREATE (x:user {name:$params['name'],lastname:$params['lastname'],wholename:$params['wholename'],initials:$params['initials'],email:$params['email'],hashed_password:$params['hashed_password'],account_type:$params['account_type'],plan:$params['plan'],paid:$params['paid'],created_on:$params['created_on'],confirmed:$params['confirmed']}) RETURN properties(x) as properties"""
        res = graph.createQuery(query,params=self.__dict__)

        return res
    
    def load_user(self):
        user = graph.query(f"MATCH (x:user) WHERE x.email='{self.usr}' RETURN properties(x) AS properties")
        if len(user) > 0:
            user = user[0]
            self.name = user['name']
            self.lastname = user['lastname']
            self.wholename = user['wholename']
            self.initials = user['initials']
            self.email = user['email']
            self.hashed_password = user['hashed_password']
            self.account_type = user['account_type']
            self.plan = user['plan']
            self.paid = user['paid']
            self.created_on = user['created_on']
            self.confirmed = user['confirmed']
            return self
        else:
            return None

    def reset_password(self,password):
        self.hashed_password = hash_text(password)
        # query to update user with email self.usr with new password
        query = f"MATCH (x:user) WHERE x.email='{self.usr}' SET x.hashed_password='{self.hashed_password}' RETURN properties(x) as properties"
        res = graph.query(query)
        if len(res) > 0:
            return True
        else:
            return False
        
    def delete_user(self):
        self.load_user(self.usr)
        if self.account_type == 'faculty':
            # query to get all courses owned by user
            query = f"MATCH (x:user)-[r:OWNS_CLASSROOM]->(y:classroom) WHERE x.email='{self.usr}' RETURN properties(y) as properties"
            courses = graph.query(query)
            for course in courses:
                # query to delete course
                query = f"MATCH (x:classroom) WHERE x.id='{course['id']}' DETACH DELETE x"
                graph.deleteQuery(query)
        
        # query to delete user with email self.usr
        query = f"MATCH (x:user) WHERE x.email='{self.usr}' DETACH DELETE x"
        graph.deleteQuery(query)
        return True

    def login_user(self,password):
        user = self.load_user()
        if user is None:
            print(f"Invalid User - {self.usr}")
            return None
        
        if not verify_hash(user.hashed_password, password):
            print(f"Invalid Password for {user.email}")
            return None
        
        print(f"User {user.email} passed authentication")
        return user
    
    def generate_confirmation_token(self):
        serializer = URLSafeTimedSerializer(secret_key)
        return serializer.dumps(self.email, salt=salt)
    
    def confirm_user(self):
        # query to update user with email self.usr with property confirmed = True
        query = f"MATCH (x:user) WHERE x.email='{self.usr}' SET x.confirmed=True RETURN properties(x) as properties"
        res = graph.query(query)
        return True
    
    def get_user_courses(self):
        self.load_user()
        if self.account_type == 'faculty':
            # query to get all courses owned by user
            query = f"MATCH (x:user)-[r:OWNS_CLASSROOM]->(y:classroom) WHERE x.email='{self.usr}' RETURN properties(y) as properties"
            courses = graph.query(query)
            return courses
        else:
            return None
        

