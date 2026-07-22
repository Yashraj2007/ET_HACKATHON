# Generated from: prepare_knowledge_base.ipynb
# Converted at: 2026-07-15T01:43:58.078Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # 📚 `prepare_knowledge_base.ipynb`
# ### Knowledge Base Preparation Pipeline — PS6: Digital Public Safety (Fraud / Scam / Counterfeiting Detection)
# 
# This notebook is **not** a model-training notebook. It builds the **RAG Knowledge Base** that your AI assistant will query at inference time.
# 
# **Pipeline:**
# 
# `Collect Documents` → `Load & Extract Text` → `Clean` → `Chunk` → `Embed` → `Attach Extended Metadata` → `Store in Vector DB` → `Test Retrieval`
# 
# **Output:** a persisted, searchable vector knowledge base (`knowledge_vector_db/`) with rich metadata — not an ML model.
# 
# ---


# ## 0. Setup & Installation
# 
# Run once. Uses:
# - `pypdf` → PDF text extraction
# - `python-docx` → Word document extraction
# - `beautifulsoup4` → HTML extraction
# - `sentence-transformers` → embeddings
# - `chromadb` → local persistent vector database
# - `scikit-learn` → keyword extraction (TF-IDF)


!pip install -q pypdf python-docx beautifulsoup4 sentence-transformers chromadb tqdm scikit-learn

import os
import re
import json
import uuid
import glob
from pathlib import Path
from datetime import datetime
from collections import Counter

from tqdm import tqdm

print("Setup complete.")

# ## 1. Configuration
# 
# Everything tunable lives here — folder paths, categories, chunk size, embedding model.
# Edit this cell only; the rest of the notebook should not need changes.


# ---------- Paths ----------
RAW_DOCS_DIR = "knowledge_docs"
PROCESSED_DIR = "processed_knowledge"
VECTOR_DB_DIR = "knowledge_vector_db"
METADATA_CONFIG_FILE = "document_metadata.json"

# ---------- Categories (folder names inside RAW_DOCS_DIR) ----------
CATEGORIES = [
    "digital_arrest",
    "trading_scam",
    "romance_scam",
    "ai_voice_scam",
    "counterfeit_currency",
    "banking_fraud",
    "social_engineering",
    "government_guidelines",
]

# ---------- Category to Scam Type Mapping ----------
CATEGORY_TO_SCAM_TYPE = {
    "digital_arrest": "Government Impersonation",
    "trading_scam": "Investment Fraud",
    "romance_scam": "Relationship Fraud",
    "ai_voice_scam": "Deepfake/Voice Cloning",
    "counterfeit_currency": "Currency Counterfeiting",
    "banking_fraud": "Financial Fraud",
    "social_engineering": "Manipulation & Phishing",
    "government_guidelines": "Official Guidelines",
}

# ---------- Chunking ----------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# ---------- Embedding model ----------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# ---------- Vector DB ----------
COLLECTION_NAME = "fraud_scam_knowledge_base"

# Create required folders
for d in [RAW_DOCS_DIR, PROCESSED_DIR, VECTOR_DB_DIR] + [
    f"{RAW_DOCS_DIR}/{c}" for c in CATEGORIES
]:
    os.makedirs(d, exist_ok=True)

print("Config loaded. Expected folder structure:")
for c in CATEGORIES:
    print(f"  {RAW_DOCS_DIR}/{c}/")

# ## 1.5 Metadata Configuration Setup
# 
# Support for extended metadata including authority, scam_type, risk_level,
# language, and keywords. You can manually specify metadata for specific documents
# or let the system auto-detect it.


# Create a template metadata config file if it doesn't exist
if not os.path.exists(METADATA_CONFIG_FILE):
    template_metadata = {
        "_README": (
            "Optional: Map filenames to metadata. System will auto-detect "
            "missing fields. Supports exact match or wildcards (*)."
        ),
        "_example_entry": {
            "source_file": "ADVISORYTAU-ADV-003.pdf",
            "authority": "I4C",
            "scam_type": "Government Impersonation",
            "language": "English",
            "risk_level": "High",
            "keywords": ["CBI", "Money Laundering", "Video Call", "Digital Arrest"],
        },
        "ADVISORYTAU-ADV-003.pdf": {
            "authority": "I4C",
            "scam_type": "Government Impersonation",
            "language": "English",
            "risk_level": "High",
            "keywords": ["CBI", "Money Laundering", "Video Call", "Digital Arrest"],
        },
        "RBI_Circular_*.pdf": {
            "authority": "RBI",
            "language": "English",
            "risk_level": "Medium",
            "scam_type": "Banking Security",
        },
    }
    with open(METADATA_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(template_metadata, f, indent=2, ensure_ascii=False)
    print(f"Created template metadata config: {METADATA_CONFIG_FILE}")
    print("  Edit this file to add manual metadata for your documents.\n")

# Load manual metadata mappings
manual_metadata = {}
if os.path.exists(METADATA_CONFIG_FILE):
    with open(METADATA_CONFIG_FILE, "r", encoding="utf-8") as f:
        manual_metadata = json.load(f)
    # Remove instruction/example keys
    manual_metadata = {
        k: v for k, v in manual_metadata.items() if not k.startswith("_")
    }
    print(f"Loaded {len(manual_metadata)} manual metadata entries")


def match_manual_metadata(filename: str) -> dict:
    """Match filename against manual metadata config (exact match and wildcards)."""
    # Exact match first
    if filename in manual_metadata:
        return manual_metadata[filename].copy()

    # Wildcard match
    for pattern, meta in manual_metadata.items():
        if "*" in pattern:
            regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
            if re.match(f"^{regex_pattern}$", filename):
                return meta.copy()

    return {}

# ## 1.6 Metadata Extraction Functions
# 
# Automatic detection of authority, language, risk level, and keyword
# extraction from document content.


def infer_authority_from_filename(filename: str) -> str:
    """Detect authority/source from filename patterns."""
    filename_upper = filename.upper()

    authority_patterns = {
        "I4C": ["I4C", "INDIAN CYBER", "CYBERCRIME COORDINATION"],
        "RBI": ["RBI", "RESERVE BANK"],
        "CERT-In": ["CERT", "CERT-IN", "COMPUTER EMERGENCY"],
        "NCRP": ["NCRP", "NATIONAL CYBERCRIME"],
        "NPCI": ["NPCI", "NATIONAL PAYMENTS"],
        "SEBI": ["SEBI", "SECURITIES", "EXCHANGE BOARD"],
        "MHA": ["MHA", "HOME AFFAIRS", "MINISTRY OF HOME"],
        "MeitY": ["MEITY", "ELECTRONICS", "INFORMATION TECHNOLOGY"],
        "Police": ["POLICE", "COMMISSIONER", "DGP"],
        "Press": ["NEWS", "REPORT", "MEDIA", "PRESS"],
    }

    for authority, patterns in authority_patterns.items():
        if any(pattern in filename_upper for pattern in patterns):
            return authority

    return "Unknown"


def detect_language(text: str) -> str:
    """Simple language detection based on character sets."""
    if not text:
        return "English"

    sample = text[:1000]

    if re.search(r"[\u0900-\u097F]", sample):
        return "Hindi"
    if re.search(r"[\u0980-\u09FF]", sample):
        return "Bengali"
    if re.search(r"[\u0A80-\u0AFF]", sample):
        return "Gujarati"
    if re.search(r"[\u0C80-\u0CFF]", sample):
        return "Kannada"
    if re.search(r"[\u0B80-\u0BFF]", sample):
        return "Tamil"

    return "English"


def infer_risk_level(category: str, text: str) -> str:
    """Infer risk level based on category and content analysis."""
    text_lower = text.lower()[:2000]

    critical_keywords = [
        "immediate arrest",
        "warrant issued",
        "legal action within",
        "account will be blocked",
        "suspended immediately",
        "criminal case",
        "money laundering case",
        "ed investigation",
    ]

    high_risk_keywords = [
        "urgent",
        "verify immediately",
        "call back now",
        "share otp",
        "provide cvv",
        "account details required",
        "government officer",
        "police",
        "income tax",
        "customs",
    ]

    if any(keyword in text_lower for keyword in critical_keywords):
        return "Critical"

    high_risk_categories = ["digital_arrest", "banking_fraud", "counterfeit_currency"]
    medium_risk_categories = ["trading_scam", "ai_voice_scam", "social_engineering"]

    if any(keyword in text_lower for keyword in high_risk_keywords):
        return "High"

    if category in high_risk_categories:
        return "High"
    elif category in medium_risk_categories:
        return "Medium"
    else:
        return "Low"


def extract_keywords_regex(text: str) -> list:
    """Extract domain-specific fraud/scam keywords using regex patterns."""
    keywords = set()

    patterns = [
        r"\b(CBI|ED|Income Tax|IT Department|Customs|Police|Court|Magistrate)\b",
        r"\b(OTP|CVV|PIN|Password|Account Number|IFSC|UPI|Net Banking)\b",
        r"\b(Digital Arrest|Video Call|KYC|Verification|Suspended|Blocked)\b",
        r"\b(Money Laundering|Fraud|Scam|Phishing|Cyber[- ]?Crime)\b",
        r"\b(Cryptocurrency|Bitcoin|Trading|Investment|Returns|Profit)\b",
        r"\b(WhatsApp|Telegram|Email|SMS|Phone Call)\b",
        r"\b(Bank Account|Credit Card|Debit Card|NEFT|RTGS|IMPS)\b",
        r"\b(Urgent|Immediate|Confidential|Secret|Limited Time)\b",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match) <= 5 and match.upper() == match:
                keywords.add(match.upper())
            else:
                keywords.add(match.title())

    return list(keywords)


def extract_keywords_tfidf(text: str, top_n: int = 10) -> list:
    """Extract top keywords using TF-IDF."""
    if not text or len(text.strip()) < 50:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        text_clean = re.sub(r"[^\w\s]", " ", text.lower())

        vectorizer = TfidfVectorizer(
            max_features=50,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.8,
        )

        tfidf_matrix = vectorizer.fit_transform([text_clean])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]

        top_indices = scores.argsort()[-top_n:][::-1]
        keywords = [
            feature_names[i].title() for i in top_indices if scores[i] > 0
        ]

        return keywords
    except Exception as e:
        print(f"  Warning: TF-IDF extraction failed: {e}")
        return []


def extract_keywords(text: str, top_n: int = 15) -> list:
    """Combine regex and TF-IDF keyword extraction."""
    regex_keywords = extract_keywords_regex(text[:3000])
    tfidf_keywords = extract_keywords_tfidf(text[:3000], top_n=10)

    seen = set()
    final_keywords = []

    for kw in regex_keywords + tfidf_keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen and len(kw) > 2:
            seen.add(kw_lower)
            final_keywords.append(kw)

        if len(final_keywords) >= top_n:
            break

    return final_keywords

# ## 2. Load Documents & Extract Raw Text
# 
# Supported formats: **PDF, DOCX, TXT, HTML**.
# 
# Drop your collected files (I4C advisories, RBI circulars, CERT-In advisories,
# verified news summaries, case studies, etc.) into the matching category folder
# under `knowledge_docs/` before running this section.


from pypdf import PdfReader
import docx
from bs4 import BeautifulSoup


def extract_text_from_pdf(filepath: str) -> str:
    text = []
    reader = PdfReader(filepath)
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text.append(page_text)
    return "\n".join(text)


def extract_text_from_docx(filepath: str) -> str:
    document = docx.Document(filepath)
    return "\n".join(p.text for p in document.paragraphs)


def extract_text_from_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text_from_html(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n")


EXTRACTORS = {
    ".pdf": extract_text_from_pdf,
    ".docx": extract_text_from_docx,
    ".txt": extract_text_from_txt,
    ".html": extract_text_from_html,
    ".htm": extract_text_from_html,
}


def load_all_documents() -> list:
    """Walk every category folder and extract raw text + basic metadata."""
    documents = []
    for category in CATEGORIES:
        folder = os.path.join(RAW_DOCS_DIR, category)
        filepaths = glob.glob(os.path.join(folder, "*"))

        for filepath in filepaths:
            ext = Path(filepath).suffix.lower()
            extractor = EXTRACTORS.get(ext)
            if not extractor:
                continue

            try:
                raw_text = extractor(filepath)
            except Exception as e:
                print(f"  Warning: Failed to read {filepath}: {e}")
                continue

            if not raw_text or not raw_text.strip():
                print(f"  Warning: No extractable text in {filepath}")
                continue

            documents.append(
                {
                    "doc_id": str(uuid.uuid4()),
                    "source_file": os.path.basename(filepath),
                    "category": category,
                    "raw_text": raw_text,
                }
            )

    return documents


documents = load_all_documents()
print(f"Loaded {len(documents)} documents across {len(CATEGORIES)} categories.\n")

# Quick per-category breakdown
counts = Counter(d["category"] for d in documents)
print("Documents per category:")
for category in CATEGORIES:
    count = counts.get(category, 0)
    print(f"  {category:<24} {count:>3} document(s)")

# ## 3. Clean the Extracted Text
# 
# Removes headers/footers/page numbers, boilerplate, extra whitespace, and links —
# keeping only the substantive content (scam description, warning signs, prevention
# tips, procedures).


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = re.sub(r"(?im)^\s*page\s*\d+(\s*of\s*\d+)?\s*$", "", text)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    text = re.sub(r"https?://\S+", "", text)

    boilerplate_patterns = [
        r"(?im)^\s*copyright.*$",
        r"(?im)^\s*all rights reserved.*$",
        r"(?im)^\s*confidential.*$",
        r"(?im)^\s*www\.\S+.*$",
    ]
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, "", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


for doc in tqdm(documents, desc="Cleaning documents"):
    doc["clean_text"] = clean_text(doc["raw_text"])

print("Cleaning complete.")
if documents:
    print("\nSample cleaned excerpt:\n")
    print(documents[0]["clean_text"][:400])

# ## 3.5 Extract Enhanced Metadata
# 
# Automatically extract extended metadata: authority, scam_type, language,
# risk_level, keywords. Manual metadata from `document_metadata.json` takes precedence
# over auto-detection.


print("\nExtracting enhanced metadata for each document...")

for doc in tqdm(documents, desc="Extracting metadata"):
    filename = doc["source_file"]
    category = doc["category"]
    text = doc["clean_text"]

    # Start with manual metadata if available
    enhanced_meta = match_manual_metadata(filename)

    # Auto-detect missing fields
    if "authority" not in enhanced_meta or not enhanced_meta["authority"]:
        enhanced_meta["authority"] = infer_authority_from_filename(filename)

    if "scam_type" not in enhanced_meta or not enhanced_meta["scam_type"]:
        enhanced_meta["scam_type"] = CATEGORY_TO_SCAM_TYPE.get(category, "General")

    if "language" not in enhanced_meta or not enhanced_meta["language"]:
        enhanced_meta["language"] = detect_language(text[:1000])

    if "risk_level" not in enhanced_meta or not enhanced_meta["risk_level"]:
        enhanced_meta["risk_level"] = infer_risk_level(category, text[:2000])

    if "keywords" not in enhanced_meta or not enhanced_meta["keywords"]:
        enhanced_meta["keywords"] = extract_keywords(text[:3000])

    # Ensure keywords is a list
    if isinstance(enhanced_meta["keywords"], str):
        enhanced_meta["keywords"] = [
            k.strip() for k in enhanced_meta["keywords"].split(",")
        ]

    doc["enhanced_metadata"] = enhanced_meta

print("Enhanced metadata extraction complete.\n")

# Show sample
if documents:
    print("Sample enhanced metadata:")
    print(
        json.dumps(
            {
                "source_file": documents[0]["source_file"],
                "category": documents[0]["category"],
                **documents[0]["enhanced_metadata"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print()

# ## 4. Split Documents into Overlapping Chunks
# 
# Long documents are split into smaller, semantically coherent pieces so retrieval
# returns precise, relevant passages instead of an entire 100-page PDF.


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list:
    """Sliding-window chunker with overlap, splitting on paragraph/sentence
    boundaries where possible so chunks don't cut mid-sentence."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        boundary = text.rfind("\n", start, end)
        if boundary == -1 or boundary <= start:
            boundary = text.rfind(". ", start, end)
        if boundary != -1 and boundary > start:
            end = boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end - overlap > start else end

    return chunks


all_chunks = []

for doc in tqdm(documents, desc="Chunking documents"):
    pieces = chunk_text(doc["clean_text"])
    for i, piece in enumerate(pieces):
        all_chunks.append(
            {
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc["doc_id"],
                "source_file": doc["source_file"],
                "category": doc["category"],
                "chunk_index": i,
                "chunk_text": piece,
                "enhanced_metadata": doc["enhanced_metadata"],
            }
        )

print(f"Created {len(all_chunks)} chunks from {len(documents)} documents.")

# ## 5. Save Cleaned & Chunked Text (Intermediate Checkpoint)
# 
# Saved as JSON so you can inspect/debug quality before spending time on embeddings.


processed_path = os.path.join(PROCESSED_DIR, "chunks.json")
with open(processed_path, "w", encoding="utf-8") as f:
    json.dump(all_chunks, f, ensure_ascii=False, indent=2)

print(f"Saved {len(all_chunks)} chunks -> {processed_path}")

# ## 6. Generate Semantic Embeddings
# 
# Each chunk is converted into a vector so meaning-based (not just keyword) search
# is possible. E.g. "never share your OTP" and "do not disclose your OTP to anyone"
# end up close together in vector space.


from sentence_transformers import SentenceTransformer

print(f"Loading embedding model: {EMBEDDING_MODEL_NAME} ...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

chunk_texts = [c["chunk_text"] for c in all_chunks]

print("Generating embeddings...")
embeddings = embedding_model.encode(
    chunk_texts,
    batch_size=32,
    show_progress_bar=True,
    convert_to_numpy=True,
)

print(f"Generated embeddings shape: {embeddings.shape}")

# ## 7. Attach Extended Metadata to Each Chunk
# 
# Metadata now includes authority, scam_type, language, risk_level,
# keywords — making answers **traceable** and **filterable** by these attributes.


for i, chunk in enumerate(all_chunks):
    enhanced = chunk["enhanced_metadata"]

    chunk["metadata"] = {
        # Core fields
        "source_file": chunk["source_file"],
        "category": chunk["category"],
        "doc_id": chunk["doc_id"],
        "chunk_index": chunk["chunk_index"],
        # Extended fields
        "authority": enhanced.get("authority", "Unknown"),
        "scam_type": enhanced.get("scam_type", "General"),
        "language": enhanced.get("language", "English"),
        "risk_level": enhanced.get("risk_level", "Medium"),
        "keywords": ", ".join(enhanced.get("keywords", [])),
        # Timestamp
        "prepared_on": datetime.now().strftime("%Y-%m-%d"),
    }

print("Extended metadata attached to all chunks.\n")
print("Example chunk metadata:")
if all_chunks:
    print(json.dumps(all_chunks[0]["metadata"], indent=2, ensure_ascii=False))

# ## 8. Build & Persist the Vector Database
# 
# Using **ChromaDB** (local, file-based, no external service needed — ideal for a
# hackathon prototype). The database stores: chunk text + embedding + metadata,
# all searchable by semantic similarity.


import chromadb

chroma_client = chromadb.PersistentClient(path=VECTOR_DB_DIR)

# Fresh collection each run (safe for repeated experimentation)
try:
    chroma_client.delete_collection(COLLECTION_NAME)
    print("Deleted existing collection (fresh start)")
except Exception:
    pass

collection = chroma_client.create_collection(name=COLLECTION_NAME)

BATCH_SIZE = 200
for start in tqdm(
    range(0, len(all_chunks), BATCH_SIZE), desc="Writing to vector DB"
):
    batch = all_chunks[start : start + BATCH_SIZE]
    collection.add(
        ids=[c["chunk_id"] for c in batch],
        embeddings=embeddings[start : start + BATCH_SIZE].tolist(),
        documents=[c["chunk_text"] for c in batch],
        metadatas=[c["metadata"] for c in batch],
    )

print(f"\nVector DB persisted at: {VECTOR_DB_DIR}")
print(f"Collection name: {COLLECTION_NAME}")
print(f"Total chunks stored: {collection.count()}")

# ## 9. Test Retrieval
# 
# Sanity-check with realistic queries and test the metadata filters
# (authority, category, risk_level) before wiring into the full RAG assistant.


def query_knowledge_base(
    query: str,
    top_k: int = 5,
    category_filter: str = None,
    authority_filter: str = None,
    risk_level_filter: str = None,
):
    """Query knowledge base with optional metadata filtering."""
    query_embedding = (
        embedding_model.encode([query], convert_to_numpy=True)[0].tolist()
    )

    # Build where clause for filtering
    where_clause = {}
    if category_filter:
        where_clause["category"] = category_filter
    if authority_filter:
        where_clause["authority"] = authority_filter
    if risk_level_filter:
        where_clause["risk_level"] = risk_level_filter

    where = where_clause if where_clause else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )

    print(f'Query: "{query}"')
    if where:
        print(f"Filters: {where}")
    print()

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    if not docs:
        print("No results found.\n")
        return results

    for rank, (doc, meta, dist) in enumerate(
        zip(docs, metas, dists), start=1
    ):
        print(f"--- Result {rank} (distance={dist:.4f}) ---")
        print(f"Source:     {meta.get('source_file', 'N/A')}")
        print(
            f"Authority:  {meta.get('authority', 'N/A')}  |  "
            f"Category: {meta.get('category', 'N/A')}"
        )
        print(
            f"Risk Level: {meta.get('risk_level', 'N/A')}  |  "
            f"Scam Type: {meta.get('scam_type', 'N/A')}"
        )

        keywords = meta.get("keywords", "")
        if keywords:
            print(
                f"Keywords:   "
                f"{keywords[:100]}{'...' if len(keywords) > 100 else ''}"
            )

        print(
            f"\n{doc[:280].strip()}{'...' if len(doc) > 280 else ''}"
        )
        print()

    return results


# Example test queries (only meaningful once real documents are loaded)
if collection.count() > 0:
    print("=" * 80)
    print("TEST 1: General Query")
    print("=" * 80 + "\n")
    query_knowledge_base(
        "Someone claiming to be CBI is asking me to stay on a video call",
        top_k=3,
    )

    print("\n" + "=" * 80)
    print("TEST 2: Filter by Authority")
    print("=" * 80 + "\n")
    query_knowledge_base(
        "banking fraud prevention", authority_filter="RBI", top_k=3
    )

    print("\n" + "=" * 80)
    print("TEST 3: Filter by Risk Level")
    print("=" * 80 + "\n")
    query_knowledge_base(
        "urgent action required", risk_level_filter="Critical", top_k=3
    )

    print("\n" + "=" * 80)
    print("TEST 4: Filter by Category")
    print("=" * 80 + "\n")
    query_knowledge_base(
        "investment scam", category_filter="trading_scam", top_k=3
    )
else:
    print(
        "Knowledge base is empty — add documents to "
        "knowledge_docs/<category>/ and re-run the notebook."
    )

# ## 10. Knowledge Base Summary Report
# 
# Generate a comprehensive summary of the knowledge base for
# documentation and quality checks.


summary = {
    "generation_info": {
        "total_documents": len(documents),
        "total_chunks": len(all_chunks),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "preparation_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    },
    "category_distribution": dict(
        Counter(d["category"] for d in documents)
    ),
    "authority_distribution": dict(
        Counter(d["enhanced_metadata"]["authority"] for d in documents)
    ),
    "risk_level_distribution": dict(
        Counter(d["enhanced_metadata"]["risk_level"] for d in documents)
    ),
    "language_distribution": dict(
        Counter(d["enhanced_metadata"]["language"] for d in documents)
    ),
    "scam_type_distribution": dict(
        Counter(d["enhanced_metadata"]["scam_type"] for d in documents)
    ),
    "metadata_fields_stored": [
        "source_file",
        "category",
        "doc_id",
        "chunk_index",
        "authority",
        "scam_type",
        "language",
        "risk_level",
        "keywords",
        "prepared_on",
    ],
}

summary_path = os.path.join(PROCESSED_DIR, "knowledge_base_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 80)
print("KNOWLEDGE BASE SUMMARY")
print("=" * 80 + "\n")
print(json.dumps(summary, indent=2, ensure_ascii=False))
print(f"\nSummary saved to: {summary_path}")

# ## 11. Final Summary
# 
# | Stage | Output | Enhanced Features |
# |---|---|---|
# | Collect | Raw files in `knowledge_docs/<category>/` | — |
# | Load & Extract | Plain text per document | — |
# | Clean | Boilerplate/noise removed | — |
# | Chunk | Overlapping segments | Extended metadata attached |
# | Embed | Vector per chunk (`all-MiniLM-L6-v2`) | — |
# | **Metadata** | **Extended metadata** | **authority, scam_type, risk_level, language, keywords** |
# | Vector DB | Persisted at `knowledge_vector_db/` | Filterable by metadata fields |
# | Test | Retrieval sanity check | Metadata-aware filtering |
# 
# **This notebook's output is a ready-to-query Vector Knowledge Base with rich metadata.**
# 
# ### Enhanced Metadata Fields
# 
# ```json
# {
#   "source_file": "ADVISORYTAU-ADV-003.pdf",
#   "category": "digital_arrest",
#   "authority": "I4C",
#   "scam_type": "Government Impersonation",
#   "language": "English",
#   "risk_level": "High",
#   "keywords": "CBI, Money Laundering, Video Call, Digital Arrest",
#   "prepared_on": "2026-07-09"
# }
# ```
# 
# ### Retrieval with Filters
# 
# ```python
# query_knowledge_base("banking security", authority_filter="RBI")
# query_knowledge_base("urgent scam", risk_level_filter="Critical")
# query_knowledge_base("fraud", category_filter="banking_fraud")
# ```
# 
# ### Next Steps
# 
# 1. Populate `knowledge_docs/<category>/` with real I4C / RBI / CERT-In / NCRP documents.
# 2. Customize `document_metadata.json` with manual metadata for specific documents.
# 3. Re-run this notebook end-to-end to rebuild the knowledge base.
# 4. Point your RAG assistant at `knowledge_vector_db/` (collection: `fraud_scam_knowledge_base`).
# 5. Use metadata filters in your retrieval logic for precise results.


print("\n" + "=" * 80)
print("KNOWLEDGE BASE PREPARATION COMPLETE")
print("=" * 80)
print(
    f"""
Outputs Generated:
  - Vector Database:  {VECTOR_DB_DIR}/
  - Processed Chunks: {processed_path}
  - Summary Report:   {summary_path}
  - Metadata Config:  {METADATA_CONFIG_FILE}

Statistics:
  - {len(documents)} documents processed
  - {len(all_chunks)} chunks created
  - {collection.count()} vectors stored

Enhanced Metadata:
  - Authority detection (I4C, RBI, CERT-In, etc.)
  - Scam type classification
  - Risk level assessment (Critical/High/Medium/Low)
  - Language detection (English/Hindi/etc.)
  - Automatic keyword extraction

Ready for RAG Integration:
  - Collection name: {COLLECTION_NAME}
  - Supports metadata filtering
  - Semantic search enabled

Next: Populate knowledge_docs/ and customize {METADATA_CONFIG_FILE}
"""
)