# Setup MONGODB Server 

## Create Docker volume to persist data
```docker volume create mongodb_data```

## Run mongodb server with Docker containers
```
docker run -d --net=host --name mongodb -e MONGODB_USERNAME=rag_app_user -e MONGODB_PASSWORD=rag_app_pwd_@123 -e MONGODB_DATABASE=rag_app_db -e ALLOW_EMPTY_PASSWORD=yes -v mongodb_data:/bitnami/mongodb bitnami/mongodb:latest
```

```
docker cp D:/Experiment/RAG_App_Tutorial/mongodb_data/mongo_init/system_design_faqs.json mongodb:/tmp/system_design_faqs.json
```

```
docker exec -it mongodb mongoimport --db rag_app_db --collection system_design_faqs --file /tmp/system_design_faqs.json --username rag_app_user --password rag_app_pwd_@123 --authenticationDatabase rag_app_db --drop --verbose  
```

# login to monogodb
```
docker exec -it mongodb mongosh --username rag_app_user --authenticationDatabase admin rag_app_db
docker exec -it mongodb mongosh --username rag_app_user --authenticationDatabase rag_app_db rag_app_db
When prompted, enter the password: rag_app_pwd_@123
```


```
show collections;
db.system_design_faqs.countDocuments();
db.system_design_faqs.find().limit(5);
db.system_design_faqs.find().limit(5).pretty();
```

```
db.<collection_name>.find();             // Finds ALL documents (use with caution on large collections!)
db.<collection_name>.find({ field: "value" }); // Finds documents matching criteria
db.<collection_name>.find().limit(N);     // Finds the first N documents
db.<collection_name>.find().pretty();     // Formats output nicely
db.<collection_name>.findOne();           // Finds the first document
db.<collection_name>.findOne({ field: "value" }); // Finds the first document matching criteria
db.<collection_name>.countDocuments();   // Count all documents
db.<collection_name>.countDocuments({ field: "value" }); // Count documents matching criteria
db.<collection_name>.insertOne({ key1: "value1", key2: "value2" }); // Insert a single document
db.<collection_name>.insertMany([ { ... }, { ... } ]); // Insert multiple documents
db.<collection_name>.updateOne({ filter_field: "value" }, { $set: { update_field: "new_value" } }); // Update first match
db.<collection_name>.updateMany({ filter_field: "value" }, { $set: { update_field: "new_value" } }); // Update all matches
db.<collection_name>.deleteOne({ field: "value" }); // Delete the first match
db.<collection_name>.deleteMany({ field: "value" }); // Delete all matches
db.system_design_faqs.insertOne({ key1: "value1", key2: "value2" });
```

```commandline
docker run -d --name mongodb \
  -p 27017:27017 \
  -e MONGODB_USERNAME=rag_app_user \
  -e MONGODB_PASSWORD=rag_app_pwd_@123 \
  -e MONGODB_DATABASE=rag_app_db \
  -v mongodb_data:/bitnami/mongodb \
  -v mongodb_init:/docker-entrypoint-initdb.d/ \
  bitnami/mongodb:latest
docker run -d --name mongodb -p 27017:27017 -e MONGODB_USERNAME=rag_app_user -e MONGODB_PASSWORD=rag_app_pwd_@123 -e MONGODB_DATABASE=rag_app_db -e ALLOW_EMPTY_PASSWORD=yes -v mongodb_data:/bitnami/mongodb -v D:/Experiment/RAG_App_Tutorial/mongodb_data/mongodb_init:/docker-entrypoint-initdb.d/ bitnami/mongodb:latest

docker run -d --name mongodb -p 27017:27017 -e MONGODB_USERNAME=rag_app_user -e MONGODB_PASSWORD=rag_app_pwd_@123 -e MONGODB_DATABASE=rag_app_db -e ALLOW_EMPTY_PASSWORD=yes -v mongodb_data:/bitnami/mongodb -v D:/Experiment/RAG_App_Tutorial/mongodb_data/mongo_init/system_design_faqs.json:/docker-entrypoint-initdb.d/ bitnami/mongodb:latest
```