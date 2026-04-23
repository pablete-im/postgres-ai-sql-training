import sys
import os

# Add the parent directory to the path so we can import database.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import get_connection

def purge_all():
    print("\n" + "="*80)
    print("🧹 EXECUTING PURGE: Cleaning up all tables and indexes from Masterclass")
    print("="*80)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # We drop the tables cascading, which automatically drops all associated indexes 
    # (HNSW, GiST, GIN, etc) and constraints.
    tables_to_drop = [
        "multimodal.facial_embeddings",
        "multimodal.multimedia_transcripts",
        "multimodal.location_events",
        "multimodal.staging_events",
        "multimodal.h3_events"
    ]
    
    for table in tables_to_drop:
        query = f"DROP TABLE IF EXISTS {table} CASCADE;"
        print(f"Executing: {query}")
        cur.execute(query)
        
    conn.commit()
    print("\n✅ All Masterclass tables and indexes have been successfully dropped.")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    user_input = input("⚠️ WARNING: This will drop all tables from the 'multimodal' schema. Are you sure? (y/n): ")
    if user_input.strip().lower() == 'y':
        purge_all()
    else:
        print("Purge cancelled.")
        sys.exit(0)
