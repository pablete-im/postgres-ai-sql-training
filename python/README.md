# Advanced PostgreSQL: Multimodal Search Masterclass for Developers

This technical training guide provides actionable SQL architectures, indexing strategies, and query patterns to implement AI-driven and geospatial features directly within PostgreSQL using `pgvector` and `PostGIS`.

## Module 1: Facial and Image Recognition (pgvector)

In this scenario, we assume you are using an external Vision model (e.g., ResNet, FaceNet, or CLIP) that outputs a dense tensor (embedding) representing visual features.

### 1.1 Table Architecture

We use the `vector(n)` data type, where `n` is the dimension of your model's output (e.g., 512 for CLIP-ViT-B-32).

```sql
CREATE TABLE facial_embeddings (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_name TEXT,
    metadata JSONB,
    s3_url TEXT,
    -- Storing the image tensor as a vector
    embedding vector(512)
);
```

Statement Breakdown:

- `gen_random_uuid()`: A native PostgreSQL v13+ function to generate UUIDv4 identifiers automatically, ensuring global uniqueness across distributed systems.
- `vector(512)`: Provided by the `pgvector` extension. It strictly enforces that every inserted array must have exactly 512 floating-point dimensions. This strictness is critical; index builds will fail if dimensions vary.

### 1.2 Data Ingestion & Mass Loading

While standard `INSERT` statements are fine for real-time inference (e.g., a user uploading a single photo), populating a database with millions of pre-computed embeddings requires mass-loading mechanisms to prevent network and planner bottlenecks.

#### A. Real-time Single Ingestion (Standard INSERT)

```sql
INSERT INTO facial_embeddings (person_name, metadata, s3_url, embedding) 
VALUES (
    'Alice Smith', 
    '{"role": "admin", "department": "security"}'::jsonb,
    's3://bucket/faces/alice.jpg', 
    '[0.012, -0.045, 0.123, ...]' -- Array of 512 floats
);
```

#### B. Bulk Ingestion using COPY (The Industry Standard)

For millions of rows, the native `COPY` command is the fastest way to stream data directly into the tables.

Example File (`faces_batch_01.csv`):

```csv
person_name,metadata,s3_url,embedding
"Bob Jones","{""role"": ""employee"", ""department"": ""HR""}","s3://bucket/faces/bob.jpg","[-0.051, 0.088, 0.201, ...]"
"Charlie Doe","{""role"": ""contractor"", ""department"": ""Facilities""}","s3://bucket/faces/charlie.jpg","[0.005, 0.011, -0.099, ...]"
"Diana Prince","{""role"": ""admin"", ""department"": ""IT""}","s3://bucket/faces/diana.jpg","[0.022, -0.015, 0.155, ...]"
```

Execution Command:

```sql
COPY facial_embeddings (person_name, metadata, s3_url, embedding) 
FROM '/path/to/faces_batch_01.csv' 
WITH (FORMAT csv, HEADER true);
```

#### C. In-Memory Streaming (psycopg2 / Python)

When your application (e.g., a Python backend) generates embeddings in real-time (like a list of Numpy arrays), writing them to a physical CSV file on disk before loading them is an anti-pattern. Instead, use `psycopg2`'s `copy_expert` with an `io.StringIO` buffer to stream the arrays directly from RAM to PostgreSQL:

```python
import io

# 1. Create an in-memory buffer
csv_file = io.StringIO()
csv_file.write("person_name,metadata,s3_url,embedding\n")
for row in data_arrays:
    # Escape double quotes for CSV format
    meta = row[1].replace('"', '""')
    csv_file.write(f'"{row[0]}","{meta}","{row[2]}","{row[3]}"\n')
csv_file.seek(0)

# 2. Stream directly to Postgres
cursor.copy_expert("COPY facial_embeddings (person_name, metadata, s3_url, embedding) FROM STDIN WITH (FORMAT csv, HEADER true)", csv_file)
```

### 1.3 Exact Similarity Queries & Distance Operators

For facial recognition and embeddings, `pgvector` provides several operators to calculate similarity.

| Operator | Meaning | Use Case | Required Index OpClass |
| :--- | :--- | :--- | :--- |
| `<->` | L2 Distance (Euclidean) | Best for embeddings where magnitude is important. | `vector_l2_ops` |
| `<#>` | Inner Product | Best for normalized embeddings (faster than Cosine). | `vector_ip_ops` |
| `<=>` | Cosine Distance | Best for text/images where angle/orientation matters. | `vector_cosine_ops` |
| `<+>` | L1 Distance (Manhattan) | Alternative geometric distance. | `vector_l1_ops` |

For this example, we'll demonstrate queries using Cosine Distance (`<=>`), Euclidean Distance (`<->`), and Inner Product (`<#>`):

```sql
-- Query 1: Find the 5 closest faces using Cosine Distance
SELECT person_name, 1 - (embedding <=> '[0.015, -0.042, 0.110, ...]') AS similarity_score
FROM facial_embeddings
ORDER BY embedding <=> '[0.015, -0.042, 0.110, ...]' ASC LIMIT 5;

-- Query 2: Find the 5 closest faces using Euclidean (L2) Distance
SELECT person_name, embedding <-> '[0.015, -0.042, 0.110, ...]' AS l2_distance
FROM facial_embeddings
ORDER BY embedding <-> '[0.015, -0.042, 0.110, ...]' ASC LIMIT 5;

-- Query 3: Find the 5 closest faces using Inner Product
SELECT person_name, (embedding <#> '[0.015, -0.042, 0.110, ...]') * -1 AS inner_product
FROM facial_embeddings
ORDER BY embedding <#> '[0.015, -0.042, 0.110, ...]' ASC LIMIT 5;
```

Statement Breakdown & Context:

- `<=>`: Computes Cosine Distance. The closer to 0, the more similar. `1 - distance` converts it to a Similarity Score.
- `<->`: Computes Euclidean distance. The raw value represents the geometric distance between two points in multidimensional space.
- `<#>`: Computes negative Inner Product. `pgvector` sorts in ascending order, so the inner product is negated internally. Multiplying by `-1` restores the original value (higher is better).

> 💡 **CRITICAL LESSON: Vector Normalization & Inner Product vs Cosine**
>
> You might notice that testing these three operators with random mock vectors produces different rankings. This happens because **Inner Product (`<#>`) factors in both the angle AND the magnitude (length) of the vector**, whereas **Cosine Distance (`<=>`) only looks at the angle**.
> 
> However, modern LLM providers (like OpenAI's `text-embedding-3`) return **normalized embeddings** by default—meaning every single vector has exactly a magnitude/length of `1.0`. 
> 
> **Mathematical Equivalency:**
> When vectors are normalized to a length of `1.0`, the formula for Inner Product (`Cosine Similarity * Length A * Length B`) becomes exactly equivalent to Cosine Similarity. 
> 
> **Why this matters for Production:**
> If your vectors are normalized, you should **always use Inner Product (`<#>`) with the `vector_ip_ops` index** because it requires fewer mathematical operations than Cosine Distance, making it computationally faster at scale.

### 1.4 Hybrid search Images + JSON metadata

In real-world applications, you rarely search *only* by vectors. Usually, you want to pre-filter your dataset using structured or semi-structured data (like JSON metadata) before calculating vector distances. This is known as **Pre-filtering Hybrid Search**.

PostgreSQL's `JSONB` type combined with a `GIN` index allows for lightning-fast metadata filtering, which drastically reduces the number of vectors the HNSW index needs to evaluate.

```sql
-- Find the most similar faces, but ONLY for people who are 'admin'
SELECT 
    person_name,
    metadata->>'department' AS department,
    1 - (embedding <=> '[0.015, -0.042, 0.110, ...]') AS similarity_score
FROM 
    facial_embeddings
WHERE 
    metadata @> '{"role": "admin"}'
ORDER BY 
    embedding <=> '[0.015, -0.042, 0.110, ...]' ASC
LIMIT 3;
```

**Execution Note**: PostgreSQL will first use the `GIN` index on the `metadata` column to quickly isolate rows where `role = admin`. Then, it will use the `HNSW` index on the `embedding` column to find the closest vectors among that filtered subset. This is significantly faster and more accurate than doing a post-filter.

### 1.5 Indexing for Production (HNSW vs IVFFlat)

To prevent Sequential Scans, you must index the vector column. We use HNSW for the best read performance. **Crucially, your index operator class MUST match the operator used in your `ORDER BY` clause.**

```sql
-- Index for Cosine Distance queries (<=>)
CREATE INDEX facial_hnsw_cosine_idx 
ON facial_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Index for L2 / Euclidean Distance queries (<->)
CREATE INDEX facial_hnsw_l2_idx 
ON facial_embeddings USING hnsw (embedding vector_l2_ops)
WITH (m = 16, ef_construction = 64);

-- Index for Inner Product queries (<#>)
CREATE INDEX facial_hnsw_ip_idx 
ON facial_embeddings USING hnsw (embedding vector_ip_ops)
WITH (m = 16, ef_construction = 64);

-- Index for JSONB Metadata filtering
CREATE INDEX facial_metadata_idx 
ON facial_embeddings USING GIN (metadata jsonb_ops);
```

Detailed Index Explanation:

- `USING hnsw`: Creates a Hierarchical Navigable Small World graph, which is currently the state-of-the-art algorithm for fast approximate nearest neighbor (ANN) searches.
- `vector_cosine_ops`: Crucial parameter. You must specify the operator class that matches your query ( `<=>` needs `vector_cosine_ops`, `<->` needs `vector_l2_ops`).
- `USING GIN`: Generalized Inverted Index. Essential for querying inside `JSONB` objects. By default, this uses the `jsonb_ops` operator class (equivalent to `USING GIN (metadata jsonb_ops)`). It indexes every key and value inside the JSON document, allowing PostgreSQL to instantly find rows matching specific metadata criteria without scanning the whole table.
  - *Default Operator Class (`jsonb_ops`)*: Supports the following operators:
    - `@>` (Contains): Finds documents containing a specific key-value pair or structure (e.g., `metadata @> '{"role": "admin"}'`). This is the most common and powerful operator for metadata filtering.
    - `?` (Exists): Checks if a specific top-level key exists in the JSON document (e.g., `metadata ? 'department'`).
    - `?|` (Exists Any): Checks if *any* of the specified keys exist in the document (e.g., `metadata ?| array['role', 'title']`).
    - `?&` (Exists All): Checks if *all* of the specified keys exist in the document (e.g., `metadata ?& array['role', 'department']`).
  - *Alternative Operator Class (`jsonb_path_ops`)*: If you only need the `@>` (Contains) operator, you can create the index as `USING GIN (metadata jsonb_path_ops)`. This creates a significantly smaller and faster index because it only indexes the paths and values, but it drops support for the `?`, `?|`, and `?&` key-existence operators.

### 1.6 Execution Instructions (Python)

To run the complete pipeline for this module (schema setup, bulk ingestion, and semantic queries), you can execute the provided Python script. 

1. Configure your database connection details in the file `python/config.ini`. Update the `host`, `admin_user`, `password`, `port`, and `database_name` as necessary.
2. Create and activate a Python virtual environment, install the dependencies, run the script, and finally deactivate the environment:

```bash
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python module1_facial/script.py
deactivate
```

## Module 2: Hybrid Search (Audio / Video Transcripts & PDFs)

This is the most complex and powerful use case: combining exact keyword matches (Full Text Search) with semantic conceptual matching (LLM Embeddings).

### 2.1 Hybrid Table Architecture & Indexes (GIN + HNSW)

```sql
CREATE TABLE multimedia_transcripts (
    media_id UUID PRIMARY KEY, -- Using media_id as PK for upsert strategies
    start_timestamp INTERVAL,
    raw_text TEXT,
    
    -- 1. Lexical: Auto-generated TSVECTOR for Full Text Search
    text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(raw_text, ''))) STORED,
    
    -- 2. Semantic: PGVector embedding (e.g., OpenAI text-embedding-3-small: 1536 dims)
    semantic_embedding vector(1536)
);

-- Index for Lexical Search (GIN)
CREATE INDEX transcript_fts_idx ON multimedia_transcripts USING GIN (text_search);

-- Index for Semantic Search (HNSW - Cosine Distance)
CREATE INDEX transcript_vector_cosine_idx ON multimedia_transcripts USING hnsw (semantic_embedding vector_cosine_ops);

-- Index for Semantic Search (HNSW - Inner Product)
-- Highly recommended for normalized embeddings (like OpenAI text-embedding-3)
CREATE INDEX transcript_vector_ip_idx ON multimedia_transcripts USING hnsw (semantic_embedding vector_ip_ops);
```

Statement Breakdown & Key Concepts:

- `tsvector`: A specialized PostgreSQL data type for Full Text Search. It stores a pre-processed, optimized list of words (lexemes) extracted from a document, ignoring stop words (like "the", "a", "is") and converting words to their root form (e.g., "running" becomes "run").
- `GENERATED ALWAYS AS (...) STORED`: This is a powerful feature (introduced in Postgres 12). It automatically calculates the `tsvector` value whenever a row is inserted or updated, and physically stores it on disk (`STORED`). You never have to manually update this column; Postgres handles it transparently.
- `to_tsvector('english', ...)`: The function that actually parses the raw text into the `tsvector` format, applying English language rules for stemming and stop words.
- `coalesce(raw_text, '')`: A safety measure. If `raw_text` is `NULL`, `to_tsvector` would fail or return `NULL`. `coalesce` replaces `NULL` with an empty string `''`, ensuring the vector generation always succeeds. In tables with multiple text columns (e.g., `title` and `body`), you often see them concatenated like `coalesce(title,'') || ' ' || coalesce(body,'')`.
- `USING GIN (text_search)`: Creates a Generalized Inverted Index. This is the engine behind fast Full Text Search, mapping every unique word to the rows where it appears, allowing instant lookups even in massive datasets.

### 2.2 Data Ingestion & Upserting (Model Upgrades)

When dealing with ML models (like speech-to-text or embedding generation), models get updated frequently. You often need to re-process transcripts and update existing records without causing duplicates. We use PostgreSQL's `UPSERT` capabilities, achieved by the `ON CONFLICT (...) DO UPDATE` SQL syntax.

This syntax allows you to perform an "insert or update" in a single atomic transaction:
1. It tries to `INSERT` the row.
2. If the `PRIMARY KEY` (media_id) already exists, it catches the constraint violation (`ON CONFLICT`).
3. Instead of failing, it executes an `UPDATE` on the specific columns you define, using the newly provided values (`EXCLUDED.column_name`).

Example File (`transcripts_v2.csv`):

```csv
media_id,start_timestamp,raw_text,semantic_embedding
"a1b2c3d4-...", "00:01:23", "We have a payment issue.", "[0.12, -0.44, 0.88, ...]"
"e5f6e7c8-...", "00:03:45", "The invoice was cancelled.", "[0.05, 0.91, -0.22, ...]"
```

Execution Command (Upsert / ON CONFLICT):

> **Why use a temporary table?** The `COPY` command is designed for incredibly fast bulk data loading, but it is "dumb" regarding conflicts: it does not support the `ON CONFLICT DO UPDATE` clause. If a single primary key violation occurs during a `COPY`, the entire transaction fails. To solve this, the standard PostgreSQL pattern is to `COPY` the data into an empty temporary table (which guarantees no conflicts and is extremely fast), and then use a standard `INSERT INTO ... SELECT ... ON CONFLICT DO UPDATE` to merge the data from the temp table into the main table.

```sql
-- Creating a temporary table for the mass upload
-- LIKE ... INCLUDING ALL ensures the temp table has the exact same structure and data types
CREATE TEMP TABLE tmp_transcripts (LIKE multimedia_transcripts INCLUDING ALL);

-- Load data rapidly into the empty temp table (No conflicts possible)
COPY tmp_transcripts (media_id, start_timestamp, raw_text, semantic_embedding) 
FROM '/path/transcripts_v2.csv' WITH (FORMAT csv, HEADER true);

-- Merge into the main table (Insert new ones, Update existing ones with new embeddings)
INSERT INTO multimedia_transcripts (media_id, start_timestamp, raw_text, semantic_embedding)
SELECT media_id, start_timestamp, raw_text, semantic_embedding FROM tmp_transcripts
ON CONFLICT (media_id) DO UPDATE SET
    raw_text = EXCLUDED.raw_text,
    semantic_embedding = EXCLUDED.semantic_embedding;
    -- Note: text_search (tsvector) updates automatically because of the GENERATED ALWAYS clause.
```

### 2.3 Pure Lexical Query (FTS)

``` sql
-- Find exact mentions of "invoice" or "payment"
SELECT 
    media_id, 
    start_timestamp, 
    raw_text,
    ts_rank(text_search, to_tsquery('english', 'invoice | payment')) AS keyword_rank
FROM 
    multimedia_transcripts
WHERE 
    text_search @@ to_tsquery('english', 'invoice | payment')
ORDER BY 
    keyword_rank DESC
LIMIT 10;
```

Statement Breakdown:

- `to_tsquery('english', 'invoice | payment')`: Converts the search string into a normalized `tsquery` object. It understands boolean operators (`|` for OR, `&` for AND, `!` for NOT) and the phrase operator (`<->` for FOLLOWED BY). It also stems the words (e.g., searching for "payments" will match "payment").
  - *Other relevant operators*: 
    - `<->` (Phrase Operator): Finds words that appear exactly adjacent to each other in the text. For example, `to_tsquery('credit <-> card')` will match "credit card" but won't match "credit for the card". You can also specify distance: `<2>` means exactly 2 words apart.
    - `plainto_tsquery()`: Treats the entire input as a single literal string (ignores boolean operators). Good for raw user input.
    - `phraseto_tsquery()`: Forces the exact word sequence by automatically inserting the `<->` phrase operator between words. Also, stop words are not simply discarded, but are accounted for by inserting <N> operators rather than <-> operators. For example, `phraseto_tsquery('the payment had an issue')` becomes `'payment' <3> 'issu'`.
    - `websearch_to_tsquery()`: Understands Google-like syntax (e.g., `"exact phrase" -exclude`). Highly recommended for user-facing search bars.
- `@@`: The Full Text Search match operator. It evaluates if the `tsvector` (the document) matches the `tsquery` (the search terms). The GIN index handles this instantly.
- `ts_rank()`: Calculates a relevance score (rank) based on how often the search terms appear in the document. 
  - *Other relevant operators*: `ts_rank_cd()` calculates the score based on the proximity of the matching words (Cover Density), which is useful if you want words that appear close together to score higher.

### 2.4 Pure Semantic Query

For typical unnormalized vectors, Cosine Distance (`<=>`) is the standard. However, modern LLM providers like OpenAI return **normalized embeddings**. For normalized embeddings, Cosine Distance is mathematically equivalent to Inner Product (`<#>`), but **Inner Product is computationally faster**.

```sql
-- 1. Query using Cosine Distance
SELECT media_id, start_timestamp, raw_text,
    1 - (semantic_embedding <=> '[0.01, -0.05, ...]') AS semantic_similarity
FROM multimedia_transcripts
ORDER BY semantic_embedding <=> '[0.01, -0.05, ...]' LIMIT 10;

-- 2. Query using Inner Product (Faster for normalized embeddings like OpenAI)
SELECT media_id, start_timestamp, raw_text,
    (semantic_embedding <#> '[0.01, -0.05, ...]') * -1 AS inner_product_similarity
FROM multimedia_transcripts
ORDER BY semantic_embedding <#> '[0.01, -0.05, ...]' LIMIT 10;
```

Statement Breakdown:

- `<=>` (Cosine Distance): Calculates the angular distance between two vectors. The result is between 0 (identical) and 2 (completely opposite). We use `1 - distance` to convert this into a more intuitive "Similarity Score" where 1.0 is a perfect match.
- `<#>` (Negative Inner Product): Calculates the inner product. `pgvector` returns this as a negative number so that `ORDER BY ... ASC` works correctly (Postgres indexes only support ascending order natively for nearest neighbor). We multiply by `-1` to get the true positive inner product score.

### 2.5 Hybrid Search: The Ultimate Query (Score Fusion)

To get the best of both worlds, we use a `CTE` (Common Table Expression) to run both queries, normalize their scores, and combine them using a weighted sum.

```sql
WITH semantic_search AS (
    SELECT 
        media_id, 
        raw_text, 
        start_timestamp,
        -- Calculate cosine similarity (0 to 1)
        1 - (semantic_embedding <=> '[0.01, -0.05, ...]') AS semantic_score
    FROM multimedia_transcripts
    -- The HNSW index resolves this ORDER BY instantly
    ORDER BY semantic_embedding <=> '[0.01, -0.05, ...]'
    LIMIT 50 -- Broad recall to ensure we have enough data to fuse
),
lexical_search AS (
    SELECT 
        media_id, 
        -- TS_RANK yields arbitrary numbers. In production, you might normalize this using advanced math, but here we capture the raw rank.
        ts_rank(text_search, to_tsquery('english', 'invoice | payment')) AS lexical_score,
        raw_text,
        start_timestamp
    FROM multimedia_transcripts
    -- The GIN index resolves this WHERE clause instantly
    WHERE text_search @@ to_tsquery('english', 'invoice | payment')
    LIMIT 50
)
-- Join and calculate final weighted score
SELECT 
    COALESCE(s.media_id, l.media_id) AS media_id,
    COALESCE(s.raw_text, l.raw_text) AS raw_text,
    COALESCE(s.start_timestamp, l.start_timestamp) AS start_timestamp,
    COALESCE(s.semantic_score, 0) AS sem_score,
    COALESCE(l.lexical_score, 0) AS lex_score,
    -- Fusion weights: 70% Semantic, 30% Lexical
    -- (Assuming lexical_score is relatively normalized for this example)
    (COALESCE(s.semantic_score, 0) * 0.7) + (COALESCE(l.lexical_score, 0) * 0.3) AS final_hybrid_score
FROM 
    semantic_search s
FULL OUTER JOIN 
    lexical_search l ON s.media_id = l.media_id
ORDER BY 
    final_hybrid_score DESC
LIMIT 10;
```

Statement Breakdown & Architectural Importance:

- `WITH ...`: Defines two isolated temporary result sets (CTEs). Postgres can execute these sub-queries highly efficiently using their respective indexes (HNSW for semantic, GIN for lexical).
- `LIMIT 50`: A critical parameter for performance. You don't fuse the entire database; you only fuse the top 50 results from each search method to save CPU cycles.
- `FULL OUTER JOIN`: Merges the two sets based on the `media_id`, ensuring we don't lose documents that scored high in one method but didn't appear in the other.
- `COALESCE()`: Handles `NULL` values. If a document was found by Semantic search but not Lexical, its Lexical score will be `NULL`. `COALESCE` converts that `NULL` to `0` so the math doesn't break.
- `(Score * Weight)`: The final ranking mechanism. You assign weights depending on the use case (e.g., in legal document search, you might give 80% to Lexical; in conversational chatbots, 80% to Semantic).

### 2.6 Hybrid Search: The Ultimate Query (RRF)

While Score Fusion (Section 2.5) works well, it has a major drawback: you are combining raw scores from completely different algorithms. Cosine Distance produces scores between 0 and 1, while `ts_rank` can produce arbitrary positive numbers. Finding the perfect normalization and weights (e.g., 0.7 vs 0.3) is extremely difficult and highly dependent on the dataset.

**Reciprocal Rank Fusion (RRF)** solves this by ignoring the raw scores entirely and focusing only on the *rank* (position) of the document in each search result. The formula is `1 / (k + rank)`, where `k` is a smoothing constant (usually 60).

```sql
WITH semantic_search AS (
    SELECT 
        media_id, 
        row_number() OVER (ORDER BY semantic_embedding <=> '[0.01, -0.05, 0.1]') as semantic_rank
    FROM multimodal.multimedia_transcripts
    ORDER BY semantic_embedding <=> '[0.01, -0.05, 0.1]' 
    LIMIT 50
), 
lexical_search AS (
    SELECT 
        media_id, 
        row_number() OVER (ORDER BY ts_rank(text_search, to_tsquery('english','invoice | payment')) DESC) AS lexical_rank
    FROM multimodal.multimedia_transcripts
    WHERE text_search @@ to_tsquery('english', 'invoice | payment')
    ORDER BY ts_rank(text_search, to_tsquery('english','invoice | payment')) DESC
    LIMIT 50
)
-- Join and calculate final weighted score using RRF
SELECT 
    COALESCE(s.media_id, l.media_id) AS media_id,
    COALESCE(1.0 / (60 + s.semantic_rank), 0.0) + COALESCE(1.0 / (60 + l.lexical_rank), 0.0) AS final_rrf_score
FROM semantic_search s
FULL OUTER JOIN lexical_search l ON s.media_id = l.media_id
ORDER BY final_rrf_score DESC 
LIMIT 10;
```

**Why RRF is preferred in production:**
- **No normalization needed**: You don't have to worry about the scale of the scores.
- **Highly robust**: It consistently yields excellent results across different datasets without tuning weights.
- **Mathematically elegant**: A document that appears at rank 1 in both searches will get a very high score, while a document that appears at rank 50 in both will get a much lower score.

### 2.7 Execution Instructions (Python)

To run the complete pipeline for the Hybrid Search module (creating GIN/HNSW indexes, upserting data, and score fusion queries), use the provided Python script.

1. Verify your database connection settings in `python/config.ini` (`host`, `admin_user`, `password`, `database_name`, `port`).
2. Activate your virtual environment, install the dependencies if needed, execute the script, and deactivate:

```bash
cd python
source venv/bin/activate
python module2_hybrid/script.py
deactivate
```

## Module 3: Geospatial Search (PostGIS)

PostGIS turns PostgreSQL into a full-fledged spatial database.

### 3.1 Table Architecture & The GiST Index

```sql
CREATE TABLE location_events (
    event_id SERIAL PRIMARY KEY,
    event_type TEXT,
    -- Store multiple types of geometries (Points, Lines, Polygons)
    geom geometry(Geometry, 4326)
);

-- Crucial: Create a GiST index for spatial queries
CREATE INDEX event_geom_idx ON location_events USING GIST (geom);
```

Statement Breakdown & Indexing Details:

- `geometry(Geometry, 4326)`: Specifies that this column will store a versatile `Geometry` type (supporting Points, Lines, Polygons). `4326` is the SRID (Spatial Reference System Identifier) for WGS 84 (Global standard for GPS coordinates and database storage).
- `USING GIST`: Generalized Search Tree. This is the mandatory index type for PostGIS. Optimized for `<->` (spatial distance) and `&&` (bounding box intersection).

### 3.2 Data Ingestion & Mass Loading

Geospatial data rarely comes one point at a time; it usually arrives in large geographic datasets (Shapefiles, GeoJSON, KML).

> 🗺️ **VISUALIZE THE DATA**: [Click here to open an interactive map](http://geojson.io/#data=data:application/json,%7B%22type%22%3A%20%22FeatureCollection%22%2C%20%22features%22%3A%20%5B%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.7038%2C%2040.4168%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Traffic%20Accident%20%28Point%29%22%2C%20%22marker-color%22%3A%20%22%23ff0000%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.701%2C%2040.415%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Street%20Market%22%2C%20%22marker-color%22%3A%20%22%2300aa00%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.715%2C%2040.421%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Road%20Block%22%2C%20%22marker-color%22%3A%20%22%2300aa00%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.6912%2C%2040.41%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Police%20Checkpoint%22%2C%20%22marker-color%22%3A%20%22%2300aa00%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.69%2C%2040.412%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Protest%20from%20GeoJSON%22%2C%20%22marker-color%22%3A%20%22%23800080%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.71%2C%2040.42%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Search%20Origin%20%28Radius%20%26%20KNN%29%22%2C%20%22marker-color%22%3A%20%22%23ffa500%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22LineString%22%2C%20%22coordinates%22%3A%20%5B%5B-3.7038%2C%2040.4168%5D%2C%20%5B-3.71%2C%2040.42%5D%2C%20%5B-3.715%2C%2040.425%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Marathon%20Route%20%28Line%29%22%2C%20%22stroke%22%3A%20%22%230000ff%22%2C%20%22stroke-width%22%3A%204%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.7%2C%2040.41%5D%2C%20%5B-3.71%2C%2040.41%5D%2C%20%5B-3.71%2C%2040.42%5D%2C%20%5B-3.7%2C%2040.42%5D%2C%20%5B-3.7%2C%2040.41%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Restricted%20Zone%20%28Polygon%29%22%2C%20%22fill%22%3A%20%22%23ff0000%22%2C%20%22fill-opacity%22%3A%200.2%2C%20%22stroke%22%3A%20%22%23ff0000%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.705%2C%2040.415%5D%2C%20%5B-3.705%2C%2040.42%5D%2C%20%5B-3.7%2C%2040.42%5D%2C%20%5B-3.7%2C%2040.415%5D%2C%20%5B-3.705%2C%2040.415%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Search%20Area%20%28Intersects%20Polygon%29%22%2C%20%22fill%22%3A%20%22%23ffa500%22%2C%20%22fill-opacity%22%3A%200.2%2C%20%22stroke%22%3A%20%22%23ffa500%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.708%2C%2040.412%5D%2C%20%5B-3.708%2C%2040.422%5D%2C%20%5B-3.698%2C%2040.422%5D%2C%20%5B-3.698%2C%2040.421%5D%2C%20%5B-3.706%2C%2040.421%5D%2C%20%5B-3.706%2C%2040.412%5D%2C%20%5B-3.708%2C%2040.412%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Complex%20Intersecting%20Zone%22%2C%20%22fill%22%3A%20%22%23800080%22%2C%20%22fill-opacity%22%3A%200.2%2C%20%22stroke%22%3A%20%22%23800080%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.708%2C%2040.412%5D%2C%20%5B-3.708%2C%2040.422%5D%2C%20%5B-3.698%2C%2040.422%5D%2C%20%5B-3.698%2C%2040.412%5D%2C%20%5B-3.708%2C%2040.412%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Bounding%20Box%20%28Complex%20Zone%29%22%2C%20%22fill%22%3A%20%22%23800080%22%2C%20%22fill-opacity%22%3A%200.0%2C%20%22stroke%22%3A%20%22%23800080%22%2C%20%22stroke-dasharray%22%3A%20%225%2C%205%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.675%2C%2040.44%5D%2C%20%5B-3.67%2C%2040.436%5D%2C%20%5B-3.672%2C%2040.43%5D%2C%20%5B-3.678%2C%2040.43%5D%2C%20%5B-3.68%2C%2040.436%5D%2C%20%5B-3.675%2C%2040.44%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Complex%20Intersecting%20Zone%202%22%2C%20%22fill%22%3A%20%22%23008080%22%2C%20%22fill-opacity%22%3A%200.2%2C%20%22stroke%22%3A%20%22%23008080%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.68%2C%2040.43%5D%2C%20%5B-3.68%2C%2040.44%5D%2C%20%5B-3.67%2C%2040.44%5D%2C%20%5B-3.67%2C%2040.43%5D%2C%20%5B-3.68%2C%2040.43%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Bounding%20Box%20%28Complex%20Zone%202%29%22%2C%20%22fill%22%3A%20%22%23008080%22%2C%20%22fill-opacity%22%3A%200.0%2C%20%22stroke%22%3A%20%22%23008080%22%2C%20%22stroke-dasharray%22%3A%20%225%2C%205%22%7D%7D%5D%7D) showing all the geometries (points, lines, polygons) that will be inserted in this module.

#### A. Real-time Single Ingestion (Points, Lines, Polygons)

```sql
-- 1. Inserting a Point (e.g., an accident)
INSERT INTO location_events (event_type, geom)
VALUES (
    'Traffic Accident (Point)', 
    ST_SetSRID(ST_MakePoint(-3.7038, 40.4168), 4326)
);

-- 2. Inserting a LineString (e.g., a route or road segment)
INSERT INTO location_events (event_type, geom)
VALUES (
    'Marathon Route (Line)', 
    ST_SetSRID(ST_GeomFromText('LINESTRING(-3.7038 40.4168, -3.7100 40.4200, -3.7150 40.4250)'), 4326)
);

-- 3. Inserting a Polygon (e.g., a restricted area)
INSERT INTO location_events (event_type, geom)
VALUES (
    'Restricted Zone (Polygon)', 
    ST_SetSRID(ST_GeomFromText('POLYGON((-3.70 40.41, -3.71 40.41, -3.71 40.42, -3.70 40.42, -3.70 40.41))'), 4326)
);
```

#### B. Bulk Ingestion from CSV via Staging Table

If you receive coordinates in a CSV, copy them to a staging table and process them in bulk.

Example File (`events_batch.csv`):

```csv
event_type,longitude,latitude
"Street Market",-3.7010,40.4150
"Road Block",-3.7150,40.4210
"Police Checkpoint",-3.6912,40.4100
```

Execution Command:

```sql
-- 1. Create the staging table (if it doesn't exist)
CREATE TABLE IF NOT EXISTS staging_events (
    event_type TEXT,
    longitude FLOAT,
    latitude FLOAT
);

-- 2. Load into the staging table
COPY staging_events (event_type, longitude, latitude) FROM '/path/events_batch.csv' CSV HEADER;

-- 3. Bulk insert with Geometry transformation
INSERT INTO location_events (event_type, geom)
SELECT 
    event_type, 
    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
FROM staging_events;
```

#### C. The Professional Toolset: `ogr2ogr`

For complex geometries (like Polygons) stored in GeoJSON, the industry standard is to use the GDAL utility ogr2ogr directly from your server's terminal:

```bash
# This automatically reads the GeoJSON, creates the table structure, and imports all data
ogr2ogr -f "PostgreSQL" PG:"dbname=mydb user=myuser" events_data.geojson -nln location_events -append
```

### 3.3 Radius / Proximity Search

```sql
-- Find events within 5km (5000 meters) of a given point
SELECT 
    event_type,
    ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)::geography) AS distance_m,
    ST_AsText(geom) as coordinates
FROM 
    location_events
WHERE 
    ST_DWithin(
        geom::geography, 
        ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)::geography, 
        5000 
    )
ORDER BY 
    distance_m ASC;
```

Statement Breakdown:

- `ST_Distance()`: Calculates the shortest distance between two geometries.
- `ST_DWithin()`: High-performance spatial function that returns `true` if two geometries are within a specified distance of one another. It automatically utilizes the GiST index to do a fast bounding-box filter before calculating precise distances, making it much faster than using `ST_Distance() < 5000` in a `WHERE` clause.
- `::geography`: **Crucial Type Cast**. In PostGIS, the `geometry` type calculates distances on a flat Cartesian plane, meaning distances for SRID 4326 (GPS coordinates) would be calculated in *degrees*, which is practically useless. By casting the column to `::geography`, we force PostGIS to calculate the distance over the spherical curvature of the Earth. This ensures that both `ST_Distance` returns the exact distance in **meters**, and that `ST_DWithin` interprets the `5000` parameter as **meters** instead of degrees.

### 3.4 Spatial Relationships (Intersection & Containment)

Beyond basic distance, PostGIS excels at evaluating relationships between complex geometries like Polygons and Lines. 

```sql
-- Query 1: Find which events (points, lines, or polygons) intersect with our target Polygon
SELECT 
    event_type,
    ST_GeometryType(geom) as shape_type
FROM location_events
WHERE ST_Intersects(
    geom,
    ST_SetSRID(ST_GeomFromText('POLYGON((-3.705 40.415, -3.705 40.420, -3.700 40.420, -3.700 40.415, -3.705 40.415))'), 4326)
);

-- Query 2: Find events fully contained inside our Restricted Zone Polygon
SELECT 
    e1.event_type as target_event,
    e2.event_type as containing_polygon
FROM location_events e1
JOIN location_events e2 
  ON e2.event_type = 'Restricted Zone (Polygon)'
WHERE ST_Contains(e2.geom, e1.geom) AND e1.event_type != 'Restricted Zone (Polygon)';
```

Statement Breakdown:

- `ST_Intersects()`: Checks if two geometries share any space. It returns true if they touch or overlap at all. It uses the GiST index perfectly.
- `ST_Contains()`: Returns true if and only if no points of the first geometry lie in the exterior of the second geometry.

### 3.5 Spatial KNN (Nearest Neighbor) & Operators

PostGIS implements specialized spatial operators that map perfectly to the GiST index.

| Operator | Meaning | Use Case | Required Index |
| :--- | :--- | :--- | :--- |
| `<->` | 2D Spatial Distance | KNN searches between geometries. | `GIST (geom)` |
| `<#>` | Bounding Box Distance | Faster, less precise bounding box distance. | `GIST (geom)` |
| `&&` | Bounding Box Intersects | Checks if bounding boxes overlap. | `GIST (geom)` |

The standard for Nearest Neighbor in PostGIS is `<->` (precise 2D distance):

```sql
-- Query 1: Find the top 3 closest events based on precise 2D distance
SELECT 
    event_type,
    ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(-3.71, 40.42), 4326)::geography) AS distance_m
FROM 
    location_events
ORDER BY 
    geom <-> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)
LIMIT 3;
```

For faster, less precise queries (especially useful for massive datasets), you can use the Bounding Box Distance (`<#>`):

```sql
-- Query 2: Find the top 3 closest events based on Bounding Box distance
SELECT 
    event_type,
    geom <#> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326) AS bbox_distance_degrees
FROM 
    location_events
ORDER BY 
    geom <#> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)
LIMIT 3;
```

> **Note on Units**: The `<#>` operator works on the 2D Cartesian plane of the underlying geometry. Because our geometries use SRID 4326 (longitude/latitude), the resulting distance is returned in **degrees**, not meters. This operator is not supported for the `geography` type.

You can also calculate the Bounding Box Distance between two complex polygons:

```sql
-- Query 3: Calculate the bounding box distance between the Restricted Zone and the Complex Zones
SELECT 
    e2.event_type AS target_polygon,
    e1.geom <#> e2.geom AS bbox_distance_degrees
FROM 
    location_events e1,
    location_events e2
WHERE 
    e1.event_type = 'Restricted Zone (Polygon)'
    AND e2.event_type LIKE 'Complex Intersecting Zone%';
```

And to check if bounding boxes overlap (Bounding Box Intersects `&&`), which is much faster than the precise `ST_Intersects` function:

```sql
-- Query 4: Find events whose bounding box overlaps with our Search Area's bounding box
SELECT 
    event_type
FROM 
    location_events
WHERE 
    geom && ST_SetSRID(ST_GeomFromText('POLYGON((-3.705 40.415, -3.705 40.420, -3.700 40.420, -3.700 40.415, -3.705 40.415))'), 4326)
    AND event_type != 'Search Area (Intersects Polygon)';
```

> **Didactic Note**: The "Complex Intersecting Zone" is an L-shaped polygon that wraps around the Search Area without actually touching it. Therefore, it will **not** appear in the results of `ST_Intersects` (precise intersection), but it **will** appear in the results of `&&` because their Bounding Boxes overlap!

### 3.6 Execution Instructions (Python)

To run the complete pipeline for this module (table creation, CSV bulk ingestion, and proximity queries), use the provided Python script.

1. Ensure your connection settings are correct in `python/config.ini` (e.g., `host`, `admin_user`, `password`).
2. Create and activate the virtual environment (if you haven't already), install the requirements, run the script, and deactivate:

```bash
cd python
source venv/bin/activate
python module3_geospatial/script.py
deactivate
```

## Module 4: H3 Spatial Index (h3-pg)

H3 is a hexagonal hierarchical geospatial indexing system developed by Uber. It is perfect for heatmaps, ride-sharing, and massive spatial aggregations.

### 4.1 Table Architecture & Indexing

```sql
CREATE TABLE h3_events (
    event_id SERIAL PRIMARY KEY,
    event_type TEXT,
    h3_index h3index
);

CREATE INDEX h3_events_idx ON h3_events (h3_index);
```

### 4.2 Data Ingestion & Transformation

You can insert data by converting standard geometry points into H3 indexes at a specific resolution (e.g., resolution 9 is roughly city-block sized).

> 🗺️ **VISUALIZE THE DATA**: [Click here to open an interactive map](http://geojson.io/#data=data:application/json,%7B%22type%22%3A%20%22FeatureCollection%22%2C%20%22features%22%3A%20%5B%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.701525021579625%2C%2040.415800000000004%5D%2C%20%5B-3.701525021579625%2C%2040.4178%5D%2C%20%5B-3.7038%2C%2040.418800000000005%5D%2C%20%5B-3.7060749784203755%2C%2040.4178%5D%2C%20%5B-3.7060749784203755%2C%2040.415800000000004%5D%2C%20%5B-3.7038%2C%2040.4148%5D%2C%20%5B-3.701525021579625%2C%2040.415800000000004%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Delivery%20Dropoff%20%28Center%29%20%26%20Search%20Origin%20%28Mathematical%20Appx%29%22%2C%20%22fill%22%3A%20%22%23ffa500%22%2C%20%22fill-opacity%22%3A%200.3%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.7038%2C%2040.4168%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Delivery%20Dropoff%20%28Center%29%20%26%20Search%20Origin%22%2C%20%22marker-color%22%3A%20%22%23ff0000%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.7015238980708762%2C%2040.449000000000005%5D%2C%20%5B-3.7015238980708762%2C%2040.451%5D%2C%20%5B-3.7038%2C%2040.452000000000005%5D%2C%20%5B-3.706076101929124%2C%2040.451%5D%2C%20%5B-3.706076101929124%2C%2040.449000000000005%5D%2C%20%5B-3.7038%2C%2040.448%5D%2C%20%5B-3.7015238980708762%2C%2040.449000000000005%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Pickup%20%28North%29%20%28Mathematical%20Appx%29%22%2C%20%22fill%22%3A%20%22%230000ff%22%2C%20%22fill-opacity%22%3A%200.3%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.7038%2C%2040.45%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Pickup%20%28North%29%22%2C%20%22marker-color%22%3A%20%22%23ff0000%22%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Polygon%22%2C%20%22coordinates%22%3A%20%5B%5B%5B-3.701526264727633%2C%2040.379000000000005%5D%2C%20%5B-3.701526264727633%2C%2040.381%5D%2C%20%5B-3.7038%2C%2040.382000000000005%5D%2C%20%5B-3.7060737352723674%2C%2040.381%5D%2C%20%5B-3.7060737352723674%2C%2040.379000000000005%5D%2C%20%5B-3.7038%2C%2040.378%5D%2C%20%5B-3.701526264727633%2C%2040.379000000000005%5D%5D%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Delivery%20Dropoff%20%28South%29%20%28Mathematical%20Appx%29%22%2C%20%22fill%22%3A%20%22%230000ff%22%2C%20%22fill-opacity%22%3A%200.3%7D%7D%2C%20%7B%22type%22%3A%20%22Feature%22%2C%20%22geometry%22%3A%20%7B%22type%22%3A%20%22Point%22%2C%20%22coordinates%22%3A%20%5B-3.7038%2C%2040.38%5D%7D%2C%20%22properties%22%3A%20%7B%22name%22%3A%20%22Delivery%20Dropoff%20%28South%29%22%2C%20%22marker-color%22%3A%20%22%23ff0000%22%7D%7D%5D%7D) visualizing the precise H3 hexagons generated by PostgreSQL alongside their real-world delivery locations.

```sql
INSERT INTO h3_events (event_type, h3_index)
VALUES (
    'Delivery Dropoff (Center)',
    h3_lat_lng_to_cell(point(40.4168, -3.7038), 9)
);
```

### 4.3 Querying H3 Data

```sql
-- Find events in the same hexagon or its immediate neighbors
SELECT 
    event_type, 
    h3_index
FROM 
    h3_events
WHERE 
    h3_are_neighbor_cells(h3_index, h3_lat_lng_to_cell(point(40.4168, -3.7038), 9))
    OR h3_index = h3_lat_lng_to_cell(point(40.4168, -3.7038), 9);
```

Statement Breakdown:

- `h3_lat_lng_to_cell(point(lat, lng), resolution)`: Converts a standard GPS coordinate into its corresponding H3 hexagon ID. We use resolution `9` to match the resolution of the data we inserted. Note that `h3-pg` expects the point in `(latitude, longitude)` order, unlike PostGIS which often expects `(longitude, latitude)`.
- `h3_are_neighbor_cells(index1, index2)`: This is the core spatial relationship function for H3. It returns `true` if the two hexagons share a boundary (i.e., they are touching). Because H3 uses a grid system, this operation is incredibly fast and avoids complex trigonometric distance calculations.
- `OR h3_index = ...`: The `h3_are_neighbor_cells` function only checks for *adjacent* hexagons, it returns `false` if you compare a hexagon with itself. Therefore, to find events in the *same* hexagon OR the surrounding ones, we must explicitly include the equality check.

### 4.4 Execution Instructions (Python)

1. Verify your database connection settings in `python/config.ini`.
2. Run the script for the new module:

```bash
cd python
source venv/bin/activate
python module4_h3/script.py
deactivate
```

## Performance Note for Developers

When storing extremely large `raw_text` (e.g., full PDF pages) alongside `vector` columns, PostgreSQL will use the TOAST mechanism to store the text out-of-line. This is good, as it prevents sequential scans on the vectors from reading massive text blocks. However, if your queries routinely `SELECT raw_text` alongside vectors in huge batches, consider decoupling the text into a separate table joined by `media_id` to maximize your `shared_buffers` efficiency during vector similarity sorts.
