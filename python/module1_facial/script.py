import sys
import os

# Add the parent directory to the path so we can import database.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection

def print_step(title, query, execution_note=None, description=None):
    print(f"\n{'-'*80}")
    print(f"STEP: {title}")
    if description:
        print(f"🔍 [DESCRIPTION]: {description}")
    print(f"{'-'*80}")
    print(f"[EXECUTING SQL]:\n{query.strip()}\n")
    if execution_note:
        print(f"💡 [EXECUTION NOTE]: {execution_note}\n")

def prompt_manual_test(psql_command):
    print(f"👉 [TRY IT MANUALLY IN PSQL]:\n  {psql_command}\n")
    user_input = input("👉 Press 'y' or 'Y' to continue, or any other key to exit: ")
    if user_input.strip().lower() != 'y':
        print("Exiting script...")
        sys.exit(0)

def setup():
    """1.1 Table Architecture & 1.4 Indexing for Production"""
    conn = get_connection()
    cur = conn.cursor()
    
    q1 = """
    CREATE TABLE IF NOT EXISTS multimodal.facial_embeddings (
        image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_name TEXT,
        metadata JSONB,
        s3_url TEXT,
        embedding vector(3) -- Note: Using 3 dimensions for this example instead of 512
    );
    """
    
    q2 = """
    CREATE INDEX IF NOT EXISTS facial_hnsw_cosine_idx 
    ON multimodal.facial_embeddings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    """
    q3 = """
    CREATE INDEX IF NOT EXISTS facial_hnsw_l2_idx 
    ON multimodal.facial_embeddings USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64);
    """
    q4 = """
    CREATE INDEX IF NOT EXISTS facial_hnsw_ip_idx 
    ON multimodal.facial_embeddings USING hnsw (embedding vector_ip_ops) WITH (m = 16, ef_construction = 64);
    """
    q5 = """
    CREATE INDEX IF NOT EXISTS facial_metadata_idx 
    ON multimodal.facial_embeddings USING GIN (metadata);
    """
    
    print_step("Creating Schema, Table, and Multiple HNSW Indexes", q1 + "\n" + q2 + "\n" + q3 + "\n" + q4 + "\n" + q5)
    
    cur.execute(q1)
    cur.execute(q2)
    cur.execute(q3)
    cur.execute(q4)
    cur.execute(q5)
    conn.commit()
    print("✅ Module 1: Schema, table, and HNSW indexes created.")
    prompt_manual_test("\\dt multimodal.*\n  \\di multimodal.*\n  \\d multimodal.facial_embeddings")
    cur.close()
    conn.close()

def load_data_a():
    """1.2.A Real-time Single Ingestion"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    INSERT INTO multimodal.facial_embeddings (person_name, metadata, s3_url, embedding) 
    VALUES ('Alice Smith', '{"role": "admin", "department": "security"}', 's3://bucket/faces/alice.jpg', '[0.012, -0.045, 0.123]')
    ON CONFLICT DO NOTHING;
    """
    
    print_step("Method A: Real-time Single Ingestion (Standard INSERT)", q, execution_note="Executed directly via cur.execute() using standard SQL INSERT")
    cur.execute(q)
    conn.commit()
    print("✅ Module 1: Real-time single ingestion completed.")
    prompt_manual_test("SELECT * FROM multimodal.facial_embeddings;")
    cur.close()
    conn.close()

def load_data_b():
    """1.2.B Bulk Ingestion using COPY"""
    conn = get_connection()
    cur = conn.cursor()
    
    # We DO NOT truncate the main table so the students see the data accumulating
    # cur.execute("TRUNCATE multimodal.facial_embeddings;")
    
    q = "COPY multimodal.facial_embeddings (person_name, metadata, s3_url, embedding) FROM '/path/to/data.csv' WITH (FORMAT csv, HEADER true);"
    print_step("Method B: Bulk Ingestion using COPY (Physical File)", q, execution_note="Executed via cur.copy_expert() reading directly from a physical CSV file on disk")
    
    csv_path = os.path.join(os.path.dirname(__file__), 'data.csv')
    with open(csv_path, 'r') as f:
        cur.copy_expert("COPY multimodal.facial_embeddings (person_name, metadata, s3_url, embedding) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    
    conn.commit()
    print("✅ Module 1: Bulk ingestion using COPY completed.")
    prompt_manual_test("SELECT count(*) FROM multimodal.facial_embeddings;")
    cur.close()
    conn.close()

def load_data_c():
    """1.2.C In-Memory Streaming (psycopg2)"""
    import io
    conn = get_connection()
    cur = conn.cursor()
    
    # Simulate a list of tuples from a numpy array / external ML model
    data = [
        ("Dave Wilson", '{"role": "employee", "department": "engineering"}', "s3://bucket/faces/dave.jpg", "[0.5, 0.1, -0.2]"),
        ("Eve Davis", '{"role": "admin", "department": "IT"}', "s3://bucket/faces/eve.jpg", "[-0.5, 0.9, 0.1]")
    ]
    
    # Create an in-memory string buffer
    csv_file = io.StringIO()
    csv_file.write("person_name,metadata,s3_url,embedding\n")
    for row in data:
        # Escape double quotes for CSV
        meta = row[1].replace('"', '""')
        csv_file.write(f'"{row[0]}","{meta}","{row[2]}","{row[3]}"\n')
    
    # Reset pointer to beginning of the buffer
    csv_file.seek(0)
    
    q = "COPY multimodal.facial_embeddings (person_name, metadata, s3_url, embedding) FROM STDIN WITH (FORMAT csv, HEADER true);"
    print_step("Method C: In-Memory Streaming (psycopg2 StringIO)", q + "\n-- Executed purely in memory, no disk I/O --", execution_note="Executed via cur.copy_expert() streaming from an in-memory StringIO buffer (No intermediate physical files)")
    
    # Stream directly from RAM
    cur.copy_expert("COPY multimodal.facial_embeddings (person_name, metadata, s3_url, embedding) FROM STDIN WITH (FORMAT csv, HEADER true)", csv_file)
    
    conn.commit()
    print("✅ Module 1: In-memory streaming completed.")
    prompt_manual_test("SELECT * FROM multimodal.facial_embeddings;")
    cur.close()
    conn.close()

def query():
    """1.3 Exact Similarity Query (Top-K KNN) with Multiple Operators"""
    conn = get_connection()
    cur = conn.cursor()
    
    q_cosine = """
    SELECT 
        person_name, 
        s3_url,
        1 - (embedding <=> '[0.015, -0.042, 0.110]') AS similarity_score
    FROM multimodal.facial_embeddings
    ORDER BY embedding <=> '[0.015, -0.042, 0.110]' ASC
    LIMIT 5;
    """
    
    q_l2 = """
    SELECT 
        person_name, 
        s3_url,
        embedding <-> '[0.015, -0.042, 0.110]' AS l2_distance
    FROM multimodal.facial_embeddings
    ORDER BY embedding <-> '[0.015, -0.042, 0.110]' ASC
    LIMIT 5;
    """
    
    q_ip = """
    SELECT 
        person_name, 
        s3_url,
        (embedding <#> '[0.015, -0.042, 0.110]') * -1 AS inner_product
    FROM multimodal.facial_embeddings
    ORDER BY embedding <#> '[0.015, -0.042, 0.110]' ASC
    LIMIT 5;
    """
    
    # 1. Cosine Distance
    print_step("Query 1: Cosine Distance (<=>)", q_cosine, description="Search the most similar faces using Cosine Distance")
    cur.execute(q_cosine)
    print("--- 🎯 COSINE RESULTS (1 = Identical, 0 = Opposite) ---")
    for row in cur.fetchall():
        print(f"Name: {row[0]:<15} | Score: {row[2]:.4f}")
    prompt_manual_test(q_cosine.strip())

    # 2. L2 / Euclidean Distance
    print_step("Query 2: Euclidean / L2 Distance (<->)", q_l2, description="Search the most similar faces using Euclidean / L2 Distance")
    cur.execute(q_l2)
    print("--- 🎯 L2 RESULTS (0 = Identical, Higher = Further) ---")
    for row in cur.fetchall():
        print(f"Name: {row[0]:<15} | L2 Dist: {row[2]:.4f}")
    prompt_manual_test(q_l2.strip())

    # 3. Inner Product
    print_step("Query 3: Inner Product (<#>)", q_ip, description="Search the most similar faces using Inner Product")
    cur.execute(q_ip)
    print("--- 🎯 INNER PRODUCT RESULTS (Higher = More Similar) ---")
    for row in cur.fetchall():
        print(f"Name: {row[0]:<15} | IP: {row[2]:.4f}")
    prompt_manual_test(q_ip.strip())
    
    cur.close()
    conn.close()

def query_hybrid_json():
    """1.4 Hybrid Search Images + JSON metadata"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    SELECT 
        person_name,
        metadata->>'department' AS department,
        1 - (embedding <=> '[0.015, -0.042, 0.110]') AS similarity_score
    FROM 
        multimodal.facial_embeddings
    WHERE 
        metadata @> '{"role": "admin"}'
    ORDER BY 
        embedding <=> '[0.015, -0.042, 0.110]' ASC
    LIMIT 3;
    """
    
    print_step("Hybrid Search (JSON Pre-filtering + Vector Cosine)", q, description="Filter by JSON metadata (role='admin') first, then find the most similar faces")
    cur.execute(q)
    
    print("--- 🎯 RESULTS (Admins most similar to vector [0.015, -0.042, 0.110]) ---")
    for row in cur.fetchall():
        print(f"Person: {row[0]:<15} | Dept: {row[1]:<12} | Sim: {row[2]:.4f}")
    prompt_manual_test(q.strip())
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 EXECUTING MODULE 1: Facial and Image Recognition (pgvector)")
    print("="*80)
    setup()
    load_data_a()
    load_data_b() # Appends new data from CSV
    load_data_c() # Appends from memory
    query()
    query_hybrid_json()
    print("\n🎉 Module 1 execution finished.\n")
