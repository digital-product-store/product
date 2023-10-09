#!/usr/bin/env python3

import os
import uuid
from decimal import Decimal
from typing import List

from elasticapm.contrib.starlette import ElasticAPM, make_apm_client

from fastapi import FastAPI, UploadFile, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel

import boto3
import sqlalchemy
from sqlalchemy import select, event, text, String, ForeignKey
from sqlalchemy.orm import (
    sessionmaker,
    Session,
    DeclarativeBase,
    Mapped,
    mapped_column,
)

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME", "product-uploads")

DB_ENDPOINT = os.getenv("DB_ENDPOINT", "localhost")
DB_USERNAME = os.getenv("DB_USERNAME", "postgres")
DB_NAME = os.getenv("DB_NAME", "postgres")

ELASTIC_APM_URL = os.getenv("ELASTIC_APM_URL", "http://localhost:8200")

awsclient = boto3.client(
    "s3",
    region_name=AWS_REGION,
)

app = FastAPI()

database_url = f"postgresql://{DB_USERNAME}@{DB_ENDPOINT}:5432/{DB_NAME}"


class Base(DeclarativeBase):
    pass


class Uploads(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_id: Mapped[uuid.UUID]
    original_name: Mapped[str] = mapped_column(String(64))


class Books(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"))
    book_name: Mapped[str] = mapped_column(String(64))
    author: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(64))
    price: Mapped[Decimal]


engine = sqlalchemy.create_engine(
    database_url, connect_args={"check_same_thread": False}
)


def get_db_auth_token():
    rds_client = boto3.client("rds", region_name=AWS_REGION)
    token = rds_client.generate_db_auth_token(
        DBHostname=DB_ENDPOINT, Port=5432, DBUsername=DB_USERNAME, Region=AWS_REGION
    )
    return token


@event.listens_for(engine, "do_connect")
def provide_token(dialect, conn_rec, cargs, cparams):
    cparams["token"] = get_db_auth_token()


def inject_db():
    session = sessionmaker(engine)
    db = session()
    try:
        yield db
    finally:
        db.close()


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
def health_check(db: Session = Depends(inject_db)):
    try:
        db.execute(text("SELECT 1"))
    except:  # noqa
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    else:
        return Response(status_code=status.HTTP_200_OK)


@app.post("/admin/api/v1/upload", status_code=201)
def upload_file(file: UploadFile, db: Session = Depends(inject_db)):
    upload_id = uuid.uuid4()
    object_id = uuid.uuid4()

    awsclient.upload_fileobj(file.file, AWS_S3_BUCKET_NAME, object_id)

    upload = Uploads(id=upload_id, object_id=object_id, original_name=file.filename)
    db.add(upload)
    db.commit()
    return {"upload_id": str(upload_id), "object_id": str(object_id)}


class BookCreate(BaseModel):
    upload_id: str
    book_name: str
    author: str
    summary: str
    price: float


class BookCreated(BookCreate):
    id: str


@app.post("/admin/api/v1/book", status_code=201)
def book_create(book: BookCreate, db: Session = Depends(inject_db)) -> BookCreated:
    book_id = uuid.uuid4()

    db_book = Books(
        id=book_id,
        upload_id=book.upload_id,
        book_name=book.book_name,
        author=book.author,
        summary=book.summary,
        price=book.price,
    )

    db.add(db_book)
    db.commit()

    output = book.model_dump()
    output["id"] = str(book_id)
    created = BookCreated(**output)
    return created


class BookListing(BaseModel):
    id: str
    book_name: str
    author: str
    summary: str
    price: float

    class Config:
        from_attributes = True


@app.get("/api/v1/books", response_model=list[BookListing])
def book_list(db: Session = Depends(inject_db)) -> List[BookListing]:
    query = select(Books)
    result = db.scalars(query).all()
    return result
