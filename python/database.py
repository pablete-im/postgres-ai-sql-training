import os
import configparser
import psycopg2
from pgvector.psycopg2 import register_vector

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    config.read(config_path)
    return config['postgresql']

def get_connection():
    config = get_config()
    
    conn = psycopg2.connect(
        host=config['host'], 
        port=config['port'],
        dbname=config['database_name'],
        user=config['admin_user'],
        password=config['password'] 
    )
    
    # Register the vector type globally for this connection
    register_vector(conn)
    return conn
