from data.db_session import Neo4jConnection
# https://stackoverflow.com/questions/55523299/best-practices-for-persistent-database-connections-in-python-when-using-flask

# Connect to db
graph = Neo4jConnection()