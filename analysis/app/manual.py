"""매뉴얼 RAG. analysis/manual/*.md를 ## 제목 단위로 잘라 bge-m3로 임베딩해 manual_chunks에 넣고, 질문과 가까운 조각을 찾는다.

    python -m app.manual    # 다시 넣기. 파일이 바뀌면 실행한다 (deploy.sh가 배포 때마다 실행)
"""
from pathlib import Path

import httpx
from sqlalchemy import text

from .config import EMBED_MODEL, OLLAMA_URL
from .database import SessionLocal

MANUAL_DIR = Path(__file__).parent.parent / "manual"
TOP_K = 2


def split_sections(markdown):
    """(제목, 내용) 목록. ## 앞의 머리말은 검색 대상이 아니다."""
    sections = []
    for block in markdown.split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        sections.append((title.strip(), body.strip()))
    return sections


def actions_from_file(cause):
    """고장 이름으로 안내서 파일에서 그 절의 조치 문장을 바로 찾는다. DB와 Ollama 없이 쓴다 (실시간 감시용)."""
    for path in sorted(MANUAL_DIR.glob("*.md")):
        for title, body in split_sections(path.read_text(encoding="utf-8")):
            if f"({cause})" in title:
                steps = next((line for line in body.splitlines() if line.startswith("조치:")), "")
                return {"section": title, "source": path.name, "steps": steps.removeprefix("조치:").strip()}
    return None


def embed(texts):
    res = httpx.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=120)
    res.raise_for_status()
    return res.json()["embeddings"]


def _vector(values):
    return "[" + ",".join(str(v) for v in values) + "]"


def search(db, question, k=TOP_K):
    """질문과 가까운 조각 k개. {section, content, source}"""
    rows = db.execute(text("""
        SELECT source, section, content FROM manual_chunks
        ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k
    """), {"v": _vector(embed([question])[0]), "k": k}).mappings().all()
    return [dict(r) for r in rows]


def section(db, name):
    """고장 이름으로 그 절을 바로 찾는다. 원인을 고른 뒤 조치를 가져올 때 쓴다 (검색 결과에 안 나올 수도 있으므로)."""
    row = db.execute(text("SELECT source, section, content FROM manual_chunks WHERE section LIKE :n LIMIT 1"),
                     {"n": f"%({name})%"}).mappings().first()
    return dict(row) if row else None


def main():
    db = SessionLocal()
    rows = []
    for path in sorted(MANUAL_DIR.glob("*.md")):
        for title, body in split_sections(path.read_text(encoding="utf-8")):
            rows.append({"source": path.name, "section": title, "content": body})
    vectors = embed([f"{r['section']}\n{r['content']}" for r in rows])

    db.execute(text("DELETE FROM manual_chunks"))
    for row, vector in zip(rows, vectors):
        db.execute(text("""
            INSERT INTO manual_chunks (source, section, content, embedding)
            VALUES (:source, :section, :content, CAST(:v AS vector))
        """), {**row, "v": _vector(vector)})
    db.commit()
    print(f"매뉴얼 {len(rows)}개 조각을 넣었습니다")


if __name__ == "__main__":
    main()
