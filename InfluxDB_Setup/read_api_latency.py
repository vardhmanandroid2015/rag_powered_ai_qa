# read_api_latency.py

from influxdb_client import InfluxDBClient
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# --- InfluxDB Configuration ---
# MAKE SURE THESE ARE SET IN YOUR .env FILE
# Use the same .env file as your writing script
url    = os.environ.get("INFLUXDB_URL", "http://localhost:8086") # Default for local testing
token  = os.environ.get("INFLUXDB_TOKEN")
org    = os.environ.get("INFLUXDB_ORG")
bucket = os.environ.get("INFLUXDB_BUCKET", "rag_app_data") # Use the same bucket as the writer script


# Validate InfluxDB config
if not all([url, token, org, bucket]):
    print("❌ InfluxDB configuration (URL, TOKEN, ORG, or BUCKET) missing. Check your .env file.")
    exit() # Exit if config is missing

# Instantiate the client
timeout_seconds = 60000
try:
    client = InfluxDBClient(url=url, token=token, org=org, timeout=timeout_seconds)
    # Optional: Verify connection health
    # print("Attempting to connect and check health...")
    # health = client.health()
    # if health.status == "pass":
    #     print(f"✅ Connected to InfluxDB at {url}. Health: {health.status}")
    # else:
    #     print(f"❌ InfluxDB health check failed: {health.message}")
    #     client.close()
    #     exit()
    print(f"✅ Initialized InfluxDB client for {url}/{bucket}")

except Exception as e:
    print(f"❌ Failed to initialize InfluxDB client: {e}")
    # Ensure client is closed even if health check is skipped
    if 'client' in locals() and client:
        client.close()
    exit()


# Instantiate a query client
query_api = client.query_api()

# --- Flux Query ---
# This query fetches the 'value' field for the 'api_latency' measurement,
# tagged with service='payment' and endpoint='/process', for the last 1 hour.
# Since the writer script is writing data with current timestamps,
# querying the last hour will retrieve the data written recently.
query = f'''
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "api_latency")
  |> filter(fn: (r) => r.service == "payment" and r.endpoint == "/process")
  |> filter(fn: (r) => r._field == "value")
  |> yield(name: "mean_latency")
'''

print(f"\nExecuting Flux query for the last 1 hour...")
print(f"\n{query}")
# print(query) # Uncomment to see the full query being executed


# --- Execute Query and Process Results ---
try:
    # The query() method returns a list of Tables
    # Each Table contains Records
    tables = query_api.query(query=query)

    if not tables:
        print("✅ Query executed successfully, but no data found in the last hour matching the criteria.")
    else:
        print(f"✅ Query executed successfully. Found {sum(len(table.records) for table in tables)} data points:")
        # Iterate through the tables and records to print the data
        for table in tables:
            # print(f"\nTable: {table.get_group_key()}") # Optional: Print table metadata
            for record in table.records:
                # Each record represents a data point (a row in the result)
                timestamp = record.get_time()
                measurement = record.get_measurement()
                field = record.get_field()
                value = record.get_value()
                service_tag = record.values['service']
                endpoint_tag = record.values['endpoint']


                # Print the details of the record
                print(f"  Time: {timestamp.isoformat()} | Measurement: {measurement} | Service: {service_tag} | Endpoint: {endpoint_tag} | {field}: {value:.2f}ms")

except Exception as e:
    print(f"❌ Error executing query: {e}")


finally:
    # Close the client
    print("\nClosing InfluxDB client...")
    try:
        if 'client' in locals() and client:
            client.close()
        print("InfluxDB client closed.")
    except Exception as e:
         print(f"Error closing client: {e}")