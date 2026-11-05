import json
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "dev_snippets.db"

Language = Literal["csharp", "python", "sql", "javascript", "htmlcss"]
Workspace = Literal["personal", "team"]


class SnippetVersion(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    date: str = Field(min_length=1, max_length=10)
    code: str


class Snippet(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    language: Language
    description: str = Field(max_length=500)
    code: str
    date: str = Field(min_length=1, max_length=10)
    workspace: Workspace
    versions: list[SnippetVersion] = Field(min_length=1)


app = FastAPI(title="DevSnippet API", version="1.0.0")


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snippets (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                language TEXT NOT NULL,
                description TEXT NOT NULL,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                workspace TEXT NOT NULL CHECK (workspace IN ('personal', 'team')),
                versions TEXT NOT NULL
            )
            """
        )


def serialize_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "language": row["language"],
        "description": row["description"],
        "code": row["code"],
        "date": row["date"],
        "workspace": row["workspace"],
        "versions": json.loads(row["versions"]),
    }


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/api/snippets", response_model=list[Snippet])
def list_snippets(workspace: Workspace = Query("personal")) -> list[dict]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT * FROM snippets WHERE workspace = ? ORDER BY date DESC, rowid DESC",
            (workspace,),
        ).fetchall()
    return [serialize_row(row) for row in rows]


@app.post("/api/snippets", response_model=Snippet, status_code=201)
def create_snippet(snippet: Snippet) -> dict:
    data = snippet.model_dump()
    try:
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO snippets (id, title, language, description, code, date, workspace, versions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["title"],
                    data["language"],
                    data["description"],
                    data["code"],
                    data["date"],
                    data["workspace"],
                    json.dumps(data["versions"], ensure_ascii=False),
                ),
            )
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Bu snippet kimliği zaten kullanılıyor.") from error
    return data


@app.put("/api/snippets/{snippet_id}", response_model=Snippet)
def update_snippet(snippet_id: str, snippet: Snippet) -> dict:
    if snippet.id != snippet_id:
        raise HTTPException(status_code=422, detail="URL kimliği ile snippet kimliği eşleşmiyor.")
    data = snippet.model_dump()
    with connect_db() as connection:
        cursor = connection.execute(
            """
            UPDATE snippets
            SET title = ?, language = ?, description = ?, code = ?, date = ?, workspace = ?, versions = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["language"],
                data["description"],
                data["code"],
                data["date"],
                data["workspace"],
                json.dumps(data["versions"], ensure_ascii=False),
                snippet_id,
            ),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Snippet bulunamadı.")
    return data


@app.delete("/api/snippets/{snippet_id}", status_code=204)
def remove_snippet(snippet_id: str, workspace: Workspace = Query("personal")) -> Response:
    with connect_db() as connection:
        cursor = connection.execute(
            "DELETE FROM snippets WHERE id = ? AND workspace = ?",
            (snippet_id, workspace),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Snippet bulunamadı.")
    return Response(status_code=204)


app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")
