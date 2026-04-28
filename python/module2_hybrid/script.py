import sys
import os

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
    """2.1 Hybrid Table Architecture & Indexes (GIN + HNSW)"""
    conn = get_connection()
    cur = conn.cursor()
    
    q1 = """
    CREATE TABLE IF NOT EXISTS multimodal.multimedia_transcripts (
        media_id UUID PRIMARY KEY,
        start_timestamp INTERVAL,
        raw_text TEXT,
        text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(raw_text, ''))) STORED,
        semantic_embedding vector(3) -- Using 3 dimensions for demo instead of 1536
    );
    """
    
    q2 = """
    CREATE INDEX IF NOT EXISTS transcript_fts_idx 
    ON multimodal.multimedia_transcripts USING GIN (text_search);
    """
    
    q3 = """
    CREATE INDEX IF NOT EXISTS transcript_vector_cosine_idx 
    ON multimodal.multimedia_transcripts USING hnsw (semantic_embedding vector_cosine_ops);
    """

    q4 = """
    CREATE INDEX IF NOT EXISTS transcript_vector_ip_idx 
    ON multimodal.multimedia_transcripts USING hnsw (semantic_embedding vector_ip_ops);
    """
    
    print_step("Creating Hybrid Table and Indexes (GIN + HNSW Cosine/IP)", q1 + "\n" + q2 + "\n" + q3 + "\n" + q4)
    
    cur.execute(q1)
    cur.execute(q2)
    cur.execute(q3)
    cur.execute(q4)
    
    conn.commit()
    print("✅ Module 2: Schema and tables created.")
    prompt_manual_test("\\dt multimodal.*\n  \\di multimodal.*\n  \\d multimodal.multimedia_transcripts")
    cur.close()
    conn.close()

def load_data():
    """2.2 Data Ingestion & Upserting"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("CREATE TEMP TABLE tmp_transcripts (LIKE multimodal.multimedia_transcripts INCLUDING ALL);")
    
    q = """
    INSERT INTO multimodal.multimedia_transcripts (media_id, start_timestamp, raw_text, semantic_embedding)
    SELECT media_id, start_timestamp, raw_text, semantic_embedding FROM tmp_transcripts
    ON CONFLICT (media_id) DO UPDATE SET
        raw_text = EXCLUDED.raw_text,
        semantic_embedding = EXCLUDED.semantic_embedding;
    """
    
    print_step("Data Ingestion & Upserting (ON CONFLICT DO UPDATE)", 
               "-- 1. Creates a TEMP table and uses COPY to stream data to it\n" +
               "-- 2. Uses UPSERT to merge the TEMP table into the main table:\n" + q,
               execution_note="Executed via cur.copy_expert() from a physical CSV into a TEMP table, followed by cur.execute() for the UPSERT logic")
    
    csv_path = os.path.join(os.path.dirname(__file__), 'data.csv')
    with open(csv_path, 'r') as f:
        cur.copy_expert("COPY tmp_transcripts (media_id, start_timestamp, raw_text, semantic_embedding) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
        
    cur.execute(q)
    
    conn.commit()
    print("✅ Module 2: Upsert logic (insert or update) completed.")
    prompt_manual_test("SELECT * FROM multimodal.multimedia_transcripts;")
    cur.close()
    conn.close()

def query_lexical():
    """2.3 Pure Lexical Query (FTS)"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    SELECT 
        media_id, 
        start_timestamp, 
        raw_text,
        ts_rank(text_search, to_tsquery('english', 'invoice | payment')) AS keyword_rank
    FROM 
        multimodal.multimedia_transcripts
    WHERE 
        text_search @@ to_tsquery('english', 'invoice | payment')
    ORDER BY 
        keyword_rank DESC
    LIMIT 10;
    """
    
    print_step("Pure Lexical Query (Full Text Search GIN)", q, description="Search for exact keyword matches ('invoice' or 'payment') using Full Text Search")
    cur.execute(q)
    
    print("--- 🎯 RESULTS ---")
    for row in cur.fetchall():
        print(f"ID: {str(row[0])[:8]}... | Rank: {row[3]:.4f} | Text: '{row[2]}'")
    prompt_manual_test(q.strip())
    cur.close()
    conn.close()

def query_semantic():
    """2.4 Pure Semantic Query"""
    conn = get_connection()
    cur = conn.cursor()
    
    q_cosine = """
    SELECT 
        media_id, 
        start_timestamp, 
        raw_text,
        1 - (semantic_embedding <=> '[0.01, -0.05, 0.1]') AS semantic_similarity
    FROM multimodal.multimedia_transcripts
    ORDER BY semantic_embedding <=> '[0.01, -0.05, 0.1]'
    LIMIT 10;
    """
    
    q_ip = """
    SELECT 
        media_id, 
        start_timestamp, 
        raw_text,
        (semantic_embedding <#> '[0.01, -0.05, 0.1]') * -1 AS inner_product
    FROM multimodal.multimedia_transcripts
    ORDER BY semantic_embedding <#> '[0.01, -0.05, 0.1]'
    LIMIT 10;
    """
    
    print_step("Pure Semantic Query (Cosine Distance <=>)", q_cosine, description="Search for conceptually similar transcripts using Cosine Distance on semantic embeddings")
    cur.execute(q_cosine)
    print("--- 🎯 COSINE RESULTS ---")
    for row in cur.fetchall():
        print(f"ID: {str(row[0])[:8]}... | Score: {row[3]:.4f} | Text: '{row[2]}'")
    prompt_manual_test(q_cosine.strip())

    print_step("Pure Semantic Query (Inner Product <#>)", q_ip, description="Search for conceptually similar transcripts using Inner Product on semantic embeddings")
    cur.execute(q_ip)
    print("--- 🎯 INNER PRODUCT RESULTS (Best for normalized embeddings) ---")
    for row in cur.fetchall():
        print(f"ID: {str(row[0])[:8]}... | IP: {row[3]:.4f} | Text: '{row[2]}'")
    prompt_manual_test(q_ip.strip())
        
    cur.close()
    conn.close()

def query_hybrid():
    """2.5 Hybrid Search: The Ultimate Query (Score Fusion)"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    WITH semantic_search AS (
        SELECT 
            media_id, 
            raw_text, 
            start_timestamp,
            1 - (semantic_embedding <=> '[0.01, -0.05, 0.1]') AS semantic_score
        FROM multimodal.multimedia_transcripts
        ORDER BY semantic_embedding <=> '[0.01, -0.05, 0.1]'
        LIMIT 50 
    ),
    lexical_search AS (
        SELECT 
            media_id, 
            ts_rank(text_search, to_tsquery('english', 'invoice | payment')) AS lexical_score,
            raw_text,
            start_timestamp
        FROM multimodal.multimedia_transcripts
        WHERE text_search @@ to_tsquery('english', 'invoice | payment')
        LIMIT 50
    )
    SELECT 
        COALESCE(s.media_id, l.media_id) AS media_id,
        COALESCE(s.raw_text, l.raw_text) AS raw_text,
        COALESCE(s.start_timestamp, l.start_timestamp) AS start_timestamp,
        COALESCE(s.semantic_score, 0) AS sem_score,
        COALESCE(l.lexical_score, 0) AS lex_score,
        (COALESCE(s.semantic_score, 0) * 0.7) + (COALESCE(l.lexical_score, 0) * 0.3) AS final_hybrid_score
    FROM 
        semantic_search s
    FULL OUTER JOIN 
        lexical_search l ON s.media_id = l.media_id
    ORDER BY 
        final_hybrid_score DESC
    LIMIT 10;
    """
    
    print_step("Hybrid Search: Score Fusion (CTE Outer Join)", q, description="Combine Lexical and Semantic scores to find the most relevant transcripts overall")
    cur.execute(q)
    
    print("--- 🎯 RESULTS ---")
    for row in cur.fetchall():
        print(f"ID: {str(row[0])[:8]}... | Sem: {row[3]:.4f} | Lex: {row[4]:.4f} | Final: {row[5]:.4f} | Text: '{row[1]}'")
    prompt_manual_test(q.strip())
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 EXECUTING MODULE 3: Hybrid Search (Audio / Video Transcripts & PDFs)")
    print("="*80)
    setup()
    load_data()
    query_lexical()
    query_semantic()
    query_hybrid()
    print("\n🎉 Module 2 execution finished.\n")
