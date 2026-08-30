# -*- coding: utf-8 -*-
"""构建招聘知识库向量索引（ChromaDB 本地持久化）。

流程：解析 knowledge_docs.md → 按段落聚合切片（约 100-200 字/片）→ embedding → 入库。
embedding 策略（两层，README 如实说明）：
1. 首选 chromadb 默认模型（all-MiniLM-L6-v2，ONNX）：需要联网下载模型；
2. 离线兜底 HashingTfidfEF：字符 1/2-gram + 稳定哈希到固定维度 + sublinear TF +
   L2 归一化。纯本地可复现，不依赖网络与第三方分词库。
当前环境默认模型下载超时（网络受限），默认使用兜底方案 --ef tfidf；
网络可用时可执行 --ef default 切换为语义模型。

用法：python rag/build_kb.py [--ef tfidf|default]
产物：rag/chroma_db/（可重建产物，不入 git）
"""
import argparse
import hashlib
import math
import re
import shutil
from pathlib import Path

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

BASE_DIR = Path(__file__).resolve().parent
DOCS_MD = BASE_DIR / "data" / "knowledge_docs.md"
DB_DIR = BASE_DIR / "chroma_db"
DIM = 512          # 兜底向量维度
CHUNK_MAX = 200    # 单片最大字符数
CHUNK_MIN = 60     # 单片最小字符数（不足则与下一段合并）

# ---------------------------------------------------------------------------
# 文档解析与切片
# ---------------------------------------------------------------------------
_DOC_HEAD = re.compile(r"^##\s*\[(\w+)\]\s*(.+?)\s*$")

def parse_docs(md_path: Path):
    """解析 markdown 知识库 → [(doc_id, title, 正文)]，正文按空行分段。"""
    docs, doc_id, title, buf = [], None, None, []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = _DOC_HEAD.match(line.strip())
        if m:
            if doc_id and buf:
                docs.append((doc_id, title, "\n".join(buf).strip()))
            doc_id, title, buf = m.group(1), m.group(2), []
        elif doc_id is not None:
            buf.append(line)
    if doc_id and buf:
        docs.append((doc_id, title, "\n".join(buf).strip()))
    return docs

def chunk_doc(text: str):
    """把一篇文档按段落聚合成若干切片（目标 CHUNK_MIN~CHUNK_MAX 字）。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > CHUNK_MAX:
            chunks.append(cur)
            cur = p
        else:
            cur = ("%s\n%s" % (cur, p)).strip()
        # 单段超长时硬切
        while len(cur) > CHUNK_MAX:
            chunks.append(cur[:CHUNK_MAX])
            cur = cur[CHUNK_MAX:]
    if len(cur) >= CHUNK_MIN or not chunks:
        if cur:
            chunks.append(cur)
    elif chunks:
        chunks[-1] = ("%s\n%s" % (chunks[-1], cur)).strip()
    return [c for c in chunks if c.strip()]

# ---------------------------------------------------------------------------
# 离线兜底 EmbeddingFunction：Hashing TF-IDF（字符 n-gram）
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")

def _ngrams(text: str):
    """产出字符级 unigram（单汉字/英文词）与 bigram 特征，模拟轻量分词。"""
    toks = _TOKEN_RE.findall(text.lower())
    feats = list(toks)
    for a, b in zip(toks, toks[1:]):
        feats.append(a + b)
    return feats

def _stable_hash(s: str) -> int:
    """md5 稳定哈希：跨进程/跨机器结果一致（内置 hash 有随机种子不可用）。"""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16)

class HashingTfidfEF(EmbeddingFunction):
    """无状态离线 embedding：hashing trick + sublinear TF + L2 归一化。"""

    def __init__(self, dim: int = DIM):
        self._dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(t) for t in input]

    def name(self) -> str:
        return "hashing_tfidf_char12_dim%d" % DIM

    def _embed(self, text: str):
        vec = [0.0] * self._dim
        counts = {}
        for f in _ngrams(text):
            counts[f] = counts.get(f, 0) + 1
        for f, c in counts.items():
            w = 1.0 + math.log(c)  # sublinear TF
            vec[_stable_hash(f) % DIM] += w
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build(ef_name: str):
    docs = parse_docs(DOCS_MD)
    if len(docs) < 20:
        raise SystemExit("【错误】知识库文档不足 20 篇，请检查 knowledge_docs.md 格式")

    if DB_DIR.exists():
        shutil.rmtree(DB_DIR)  # 可重建产物：整库重建保证幂等
    client = chromadb.PersistentClient(path=str(DB_DIR))
    ef = HashingTfidfEF() if ef_name == "tfidf" else None
    col = client.get_or_create_collection(
        "hr_kb", metadata={"hnsw:space": "cosine"}, embedding_function=ef)

    ids, docs_txt, metas = [], [], []
    for doc_id, title, body in docs:
        for i, ck in enumerate(chunk_doc(body), 1):
            ids.append("%s_%02d" % (doc_id, i))
            docs_txt.append(ck)
            metas.append({"doc_id": doc_id, "title": title, "chunk": i})
    col.add(ids=ids, documents=docs_txt, metadatas=metas)

    print("【步骤1】解析文档：%d 篇" % len(docs))
    print("【步骤2】切片入库：%d 片（目标 %d~%d 字/片）" % (len(ids), CHUNK_MIN, CHUNK_MAX))
    print("【步骤3】embedding：%s → %d 维" % (ef.name() if ef else "chromadb 默认 all-MiniLM-L6-v2", len(col.get(ids[0:1], include=["embeddings"])["embeddings"][0])))
    print("【完成】ChromaDB 持久化目录：%s" % DB_DIR)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建 HR 知识库向量索引")
    ap.add_argument("--ef", choices=["tfidf", "default"], default="tfidf",
                    help="embedding 方案：tfidf=离线兜底（默认），default=联网下载 MiniLM")
    args = ap.parse_args()
    build(args.ef)
