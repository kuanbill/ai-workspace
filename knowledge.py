import hashlib
import json
import math
import os
import re
import shutil
import zipfile
from datetime import datetime

from data.db import KB_DIR, get_knowledge_docs, update_knowledge_vector_status

LOCAL_VECTOR_PATH = os.path.join(KB_DIR, "local_vectors.jsonl")
LOCAL_VECTOR_DIMENSIONS = 384


def read_text_file(file_path: str) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            with open(file_path, "r", encoding=encoding) as file_handle:
                return file_handle.read()
        except UnicodeDecodeError:
            continue
    with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
        return file_handle.read()


def split_text_chunks(text: str, max_chars: int = 900, overlap: int = 150):
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(paragraph):
                chunk = paragraph[start : start + max_chars].strip()
                if chunk:
                    chunks.append(chunk)
                start += max_chars - overlap
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = paragraph

    if current:
        chunks.append(current.strip())
    return chunks


def tokenize_for_vector(text: str):
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", lowered)
    return tokens


def embed_text_sparse(text: str):
    vector = {}
    for token in tokenize_for_vector(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % LOCAL_VECTOR_DIMENSIONS
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[index] = vector.get(index, 0.0) + sign

    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {str(index): round(value / norm, 6) for index, value in vector.items() if value}


def sparse_cosine_similarity(left, right) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(index, 0.0) for index, value in left.items())


def append_local_vectors(doc_id: int, filename: str, chunks) -> int:
    if not chunks:
        return 0

    with open(LOCAL_VECTOR_PATH, "a", encoding="utf-8") as file_handle:
        for index, chunk in enumerate(chunks):
            record = {
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": index,
                "text": chunk,
                "embedding": embed_text_sparse(chunk),
                "created_at": datetime.now().isoformat(),
            }
            file_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(chunks)


def vectorize_knowledge_doc(doc_id: int, filename: str, content: str) -> int:
    chunks = split_text_chunks(content)
    chunk_count = append_local_vectors(doc_id, filename, chunks)
    update_knowledge_vector_status(doc_id, chunk_count, "ready" if chunk_count else "empty")
    return chunk_count


def search_local_knowledge(query: str, limit: int = 5):
    if not os.path.exists(LOCAL_VECTOR_PATH):
        return []

    query_vector = {int(index): value for index, value in embed_text_sparse(query).items()}
    if not query_vector:
        return []

    matches = []
    with open(LOCAL_VECTOR_PATH, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            vector = {int(index): value for index, value in record.get("embedding", {}).items()}
            score = sparse_cosine_similarity(query_vector, vector)
            if score > 0:
                matches.append((score, record))

    matches.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": score,
            "filename": record.get("filename", ""),
            "text": record.get("text", ""),
            "chunk_index": record.get("chunk_index", 0),
        }
        for score, record in matches[:limit]
    ]


def build_knowledge_context(query: str, limit: int = 5):
    matches = search_local_knowledge(query, limit=limit)
    if not matches:
        return "", []

    sections = []
    for index, match in enumerate(matches, start=1):
        sections.append(
            f"[知識片段 {index}] 來源: {match['filename']} / chunk {match['chunk_index']} / score {match['score']:.3f}\n"
            f"{match['text']}"
        )
    return "\n\n".join(sections), matches


def get_local_vector_stats() -> int:
    if not os.path.exists(LOCAL_VECTOR_PATH):
        return 0
    count = 0
    with open(LOCAL_VECTOR_PATH, "r", encoding="utf-8") as file_handle:
        for _line in file_handle:
            count += 1
    return count


KB_BACKUP_DIR = os.path.join(KB_DIR, "backups")


def backup_knowledge(target_path: str) -> str:
    os.makedirs(KB_BACKUP_DIR, exist_ok=True)
    filepath = target_path or os.path.join(KB_BACKUP_DIR, f"knowledge_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(LOCAL_VECTOR_PATH):
            zf.write(LOCAL_VECTOR_PATH, "local_vectors.jsonl")
        sources_dir = os.path.join(KB_DIR, "sources")
        if os.path.isdir(sources_dir):
            for root, _dirs, files in os.walk(sources_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arc = os.path.relpath(full, KB_DIR)
                    zf.write(full, arc)
        docs = get_knowledge_docs()
        docs_export = []
        for d in docs:
            docs_export.append({
                "id": d[0], "filename": d[1], "content": d[2],
                "uploaded_at": d[3], "source_path": d[4] if len(d) > 4 else "",
                "chunk_count": d[5] if len(d) > 5 else 0,
                "vector_status": d[6] if len(d) > 6 else "",
                "vectorized_at": d[7] if len(d) > 7 else "",
            })
        zf.writestr("knowledge_docs.json", json.dumps(docs_export, ensure_ascii=False, indent=2))
    return filepath


def restore_knowledge(backup_path: str) -> tuple[bool, str]:
    if not os.path.exists(backup_path):
        return False, "備份檔不存在"
    try:
        with zipfile.ZipFile(backup_path, "r") as zf:
            for name in zf.namelist():
                target = os.path.join(KB_DIR, name)
                parent = os.path.dirname(target)
                os.makedirs(parent, exist_ok=True)
                if name.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                else:
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
        return True, "還原完成，請重新啟動應用程式以載入向量資料"
    except Exception as exc:
        return False, f"還原失敗: {exc}"
