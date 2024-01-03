import os

from neo4j import GraphDatabase, RoutingControl
# https://stackoverflow.com/questions/55523299/best-practices-for-persistent-database-connections-in-python-when-using-flask

class Neo4jConnection:
    def __init__(self):
        self.app = None
        self.driver = None
        

    def init_app(self,app):
        self.app = app
        if not self.driver:
            self.connect()
        self.driver.verify_connectivity()

        return self.driver

    def connect(self):
        cloud = os.getenv('CLOUD',False)
        self.user = os.getenv("NEO4JUSER",'')
        self.pword = os.getenv("PWORD",'')
        self.graphuri = os.getenv('GRAPHURI',"")
        if (cloud==True) or (cloud=="True"):
            self.driver = GraphDatabase.driver(self.graphuri, auth=(self.user, self.pword))
            print('established connection to aura')
        else:
            self.driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=('neo4j', 'test1234'))

        return self.driver

    def get_db(self):
        if not self.driver:
            return self.connect()
        return self.driver

    def close_db(self):
        if self.driver:
            self.driver.close()
            self.driver = None

    def query(self,query):
        with self.driver.session() as session:
            results = self.driver.execute_query(query, database="neo4j",result_transformer_=lambda r: r.value("properties"))
        return results
    
    def queryWithParams(self,query,params):
        with self.driver.session() as session:
            results = self.driver.execute_query(query, params=params, database="neo4j",result_transformer_=lambda r: r.value("properties"))
        return results
    
    def createQuery(self,query,params):
        with self.driver.session() as session:
            results = self.driver.execute_query(query, params=params, database="neo4j",result_transformer_=lambda r: r.value("properties"))
        return results
    
    def deleteQuery(self,query):
        with self.driver.session() as session:
            self.driver.execute_query(query, database="neo4j")
        return