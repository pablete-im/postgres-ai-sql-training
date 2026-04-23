# Tanzu PostgreSQL Infrastructure & Multimodal Search Masterclass

This repository serves a dual purpose: providing an automated infrastructure-as-code deployment for a modern PostgreSQL environment and offering a comprehensive developer masterclass on advanced PostgreSQL multimodal capabilities.

## Repository Overview

The repository is structured into two main domains:

1. **[Ansible Infrastructure](./ansible/README.md)**: Playbooks to deploy PostgreSQL 18.3 on Rocky Linux 9, configuring client/server nodes, securely handling secrets using Ansible Vault, and installing critical AI/spatial extensions (`pgvector` and `PostGIS`).
2. **[Python Masterclass](./python/README.md)**: A collection of Python scripts and datasets that interact with the deployed PostgreSQL database. This masterclass covers AI vector embeddings, geospatial searches, and advanced hybrid search architectures.

---

## 1. Ansible Infrastructure Deployment

The `ansible/` directory contains all the automation needed to spin up your PostgreSQL server and configure your clients.

**Key Features:**
- Automated installation of PostgreSQL 18.3, `pgvector`, and `PostGIS`.
- Centralized configuration using `group_vars`.
- Encrypted secrets management using Ansible Vault.
- Tag-based execution to isolate server and client deployments.

👉 **[Go to the Ansible Deployment Guide](./ansible/README.md)**

---

## 2. Advanced PostgreSQL: Multimodal Search Masterclass for Developers

The `python/` directory contains the Python project designed to teach you how to build modern, AI-driven applications directly inside PostgreSQL.

**Modules Covered:**
- **Module 1: Facial and Image Recognition (pgvector)**: Understand `vector` data types, HNSW indexes, distance operators (Cosine, L2, Inner Product), and in-memory streaming ingestion.
- **Module 2: Geospatial Search (PostGIS)**: Work with `geometry` types, GiST indexes, `ST_DWithin` radius proximity, and spatial KNN searches using CSVs and GeoJSON.
- **Module 3: Hybrid Search (Text & Semantic)**: Combine Full Text Search (Lexical GIN indexes) with LLM Embeddings (Semantic HNSW vector indexes) using PostgreSQL CTEs and score fusion.

👉 **[Go to the Multimodal Search Masterclass Guide](./python/README.md)**