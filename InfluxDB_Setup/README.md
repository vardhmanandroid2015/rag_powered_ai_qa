# Setup InfluxDB V2 with Docker Image
```
docker run -d --name influxdb2_tutorial --net=host --mount type=volume,source=influxdb2-tutorial-data,target=/var/lib/influxdb2 --mount type=volume,source=influxdb2-tutorial-config,target=/etc/influxdb2 --env DOCKER_INFLUXDB_INIT_MODE=setup --env DOCKER_INFLUXDB_INIT_USERNAME=influxtutorial --env DOCKER_INFLUXDB_INIT_PASSWORD=InfluxTutorial@123# --env DOCKER_INFLUXDB_INIT_ORG=InfluxTutorial --env DOCKER_INFLUXDB_INIT_BUCKET=first_bucket influxdb:2
```

# For Explanation
```
docker run -d --name influxdb2_tutorial 
--net=host 
--mount type=volume,source=influxdb2-tutorial-data,target=/var/lib/influxdb2
--mount type=volume,source=influxdb2-tutorial-config,target=/etc/influxdb2 
--env DOCKER_INFLUXDB_INIT_MODE=setup 
--env DOCKER_INFLUXDB_INIT_USERNAME=influxtutorial 
--env DOCKER_INFLUXDB_INIT_PASSWORD=InfluxTutorial@123# 
--env DOCKER_INFLUXDB_INIT_ORG=InfluxTutorial 
--env DOCKER_INFLUXDB_INIT_BUCKET=first_bucket 
influxdb:2
```