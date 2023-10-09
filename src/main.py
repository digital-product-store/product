#!/usr/bin/env python3

import os
import uuid
from typing import List

from elasticapm.contrib.starlette import ElasticAPM, make_apm_client

from fastapi import FastAPI, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import boto3
import databases
import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy import select

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME", "product-uploads")

DB_ENDPOINT = os.getenv("DB_ENDPOINT", "localhost:5432")
DB_USERNAME = os.getenv("DB_USERNAME", "postgres")
DB_NAME = os.getenv("DB_NAME", "postgres")

ELASTIC_APM_URL = os.getenv("ELASTIC_APM_URL", "http://localhost:8200")

rds_client = boto3.client("rds", region_name=AWS_REGION)
token = rds_client.generate_db_auth_token(
    DBHostname=DB_ENDPOINT, Port=5432, DBUsername=DB_USERNAME, Region=AWS_REGION
)
database_url = f"postgresql://{DB_USERNAME}:{token}@{DB_ENDPOINT}:5432/{DB_NAME}"

awsclient = boto3.client(
    "s3",
    region_name=AWS_REGION,
)

app = FastAPI()

database = databases.Database(database_url)

metadata = sqlalchemy.MetaData()
uploads = sqlalchemy.Table(
    "uploads",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sqlalchemy.Column("object_id", postgresql.UUID, nullable=False),
    sqlalchemy.Column("original_name", sqlalchemy.String, nullable=False),
)
books = sqlalchemy.Table(
    "books",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sqlalchemy.Column(
        "upload_id",
        postgresql.UUID,
        sqlalchemy.ForeignKey("uploads.id"),
        nullable=False,
    ),
    sqlalchemy.Column("book_name", sqlalchemy.VARCHAR, nullable=False),
    sqlalchemy.Column("author", sqlalchemy.VARCHAR, nullable=False),
    sqlalchemy.Column("summary", sqlalchemy.VARCHAR, nullable=False),
    sqlalchemy.Column("price", sqlalchemy.DECIMAL, nullable=False),
)

engine = sqlalchemy.create_engine(
    database_url, connect_args={"check_same_thread": False}
)


@app.on_event("startup")
async def startup():
    # init db
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


# TODO: use env var for APM SERVER URL
apm = make_apm_client(
    {
        "SERVICE_NAME": "product",
        "SERVER_URL": ELASTIC_APM_URL,
        "CAPTURE_HEADERS": True,
        "CAPTURE_BODY": "all",
    }
)
app.add_middleware(ElasticAPM, client=apm)


@app.get("/_health")
async def health_check():
    return Response(status_code=200)


@app.post("/admin/api/v1/upload", status_code=201)
async def upload_file(file: UploadFile):
    upload_id = str(uuid.uuid4())
    object_id = str(uuid.uuid4())

    awsclient.upload_fileobj(file.file, AWS_S3_BUCKET_NAME, object_id)

    query = uploads.insert().values(
        id=upload_id, object_id=object_id, original_name=file.filename
    )
    await database.execute(query)
    return {"upload_id": str(upload_id), "object_id": object_id}


class BookCreate(BaseModel):
    upload_id: str
    book_name: str
    author: str
    summary: str
    price: float


class BookCreated(BookCreate):
    id: str


@app.post("/admin/api/v1/book", status_code=201)
async def book_create(book: BookCreate) -> BookCreated:
    book_id = str(uuid.uuid4())
    query = books.insert().values(
        id=book_id,
        upload_id=book.upload_id,
        book_name=book.book_name,
        author=book.author,
        summary=book.summary,
        price=book.price,
    )
    await database.execute(query)
    output = book.model_dump()
    output["id"] = book_id
    created = BookCreated(**output)
    return created


class BookListing(BaseModel):
    id: str
    book_name: str
    author: str
    summary: str
    price: float


@app.get("/api/v1/books")
async def book_list() -> List[BookListing]:
    query = books.select()
    result = await database.fetch_all(query)
    output = list(
        map(
            lambda r: BookListing.model_construct(
                id=str(r.id),
                book_name=r.book_name,
                author=r.author,
                summary=r.summary,
                price=r.price,
            ),
            result,
        )
    )
    return output


class BookDetail(BaseModel):
    id: str
    upload_id: str
    object_id: str
    original_name: str
    book_name: str
    author: str
    summary: str
    price: float


@app.get("/_private/api/v1/books/{uuid}")
async def book_detail(uuid: str) -> BookDetail:
    query = (
        select(
            books.c.id,
            books.c.upload_id,
            uploads.c.object_id,
            uploads.c.original_name,
            books.c.book_name,
            books.c.author,
            books.c.summary,
            books.c.price,
        )
        .join(uploads)
        .where(books.c.id == uuid)
    )

    result = await database.fetch_one(query)
    if result is None:
        return Response(status_code=404)

    output = BookDetail.model_construct(
        id=str(result.id),
        upload_id=str(result.upload_id),
        object_id=str(result.object_id),
        original_name=result.original_name,
        book_name=result.book_name,
        author=result.author,
        summary=result.summary,
        price=result.price,
    )
    return output
