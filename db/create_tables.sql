CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS uploads (
    id uuid DEFAULT uuid_generate_v4(),
	object_id uuid NOT NULL,
	original_name VARCHAR NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS books (
    id uuid DEFAULT uuid_generate_v4(),
	upload_id uuid NOT NULL,
	book_name VARCHAR NOT NULL,
	author VARCHAR NOT NULL,
	summary VARCHAR NOT NULL,
	price DECIMAL NOT NULL,
	PRIMARY KEY (id),
    CONSTRAINT fk_upload_id FOREIGN KEY(upload_id) REFERENCES uploads(id)
);
