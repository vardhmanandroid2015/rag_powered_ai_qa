# Setup Postgresql Server 

## Create Docker volume to persist data
```docker create volume rag_knowledge_base```

## Run postgresql server with Docker containers
```
docker run -d --net=host --name postgres -e POSTGRES_USER=rag_app -e POSTGRES_PASSWORD='rag_app_pwd_@123' -v rag_knowledge_base:/var/lib/postgresql/data -v .\db_architect_qa.sql:/var/lib/postgresql/ postgres:latest
docker run -d --net=host --name postgres -e POSTGRES_USER=rag_app -e POSTGRES_PASSWORD='rag_app_pwd_@123' -v rag_knowledge_base:/var/lib/postgresql/data postgres:latest
```

## Create table
```
CREATE TABLE faqs (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL
);
```

## Standard tables to be created in future
```
-- Create the topics table
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

-- Create the questions table
CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL -- Initially empty for provided data
);
```