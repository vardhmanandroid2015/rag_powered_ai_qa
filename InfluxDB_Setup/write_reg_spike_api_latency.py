# write_dummy_api_latency.py (Writing Current Data - Repeating Spikes)

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS # Still using SYNCHRONOUS for simplicity per write
from datetime import datetime, timedelta
import time # Make sure time is imported
import random
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# --- InfluxDB Configuration ---
# MAKE SURE THESE ARE SET IN YOUR .env FILE
# Example .env:
# INFLUXDB_URL=http://localhost:8086
# INFLUXDB_TOKEN=YOUR_INFLUXDB_TOKEN
# INFLUXDB_ORG=InfluxTutorial
# INFLUXDB_BUCKET=rag_app_data # Or your actual bucket name

url    = os.environ.get("INFLUXDB_URL", "http://localhost:8086") # Default for local testing
token  = os.environ.get("INFLUXDB_TOKEN")
org    = os.environ.get("INFLUXDB_ORG")
bucket = os.environ.get("INFLUXDB_BUCKET", "rag_app_data") # Use your RAG data bucket or a specific monitoring bucket


# Validate InfluxDB config
if not all([url, token, org, bucket]):
    print("❌ InfluxDB configuration (URL, TOKEN, ORG, or BUCKET) missing. Check your .env file.")
    exit() # Exit if config is missing

# Instantiate the client
# Use timeout in seconds (60000 milliseconds = 60 seconds)
TIMEOUT_MILLISECONDS = 60000  # Let's use 60 seconds, the unit is seconds for the client constructor
try:
    client = InfluxDBClient(url=url, token=token, org=org, timeout=TIMEOUT_MILLISECONDS)
    # Optional: Verify connection health
    # print("Attempting to connect and check health...")
    # health = client.health()
    # if health.status == "pass":
    #     print(f"✅ Connected to InfluxDB at {url}. Health: {health.status}")
    # else:
    #     print(f"❌ InfluxDB health check failed: {health.message}")
    #     client.close()
    #     exit()
    print(f"✅ Initialized InfluxDB client for {url}/{bucket} with timeout {TIMEOUT_MILLISECONDS}s")

except Exception as e:
    print(f"❌ Failed to initialize InfluxDB client: {e}")
    # Ensure client is closed even if health check is skipped
    if 'client' in locals() and client:
        client.close()
    exit()

# Instantiate a write client
# We use SYNCHRONOUS for simplicity per write in this example.
write_api = client.write_api(write_options=SYNCHRONOUS)


# --- Data Generation Parameters ---
measurement_name = "api_latency"
service_name = "payment"
endpoint_name = "/process" # Specific endpoint
normal_latency_range = (50, 150) # Normal latency in ms
spike_latency_range = (400, 600) # Spike latency in ms
interval_seconds = 5 # How often to generate and write a data point (data granularity)


# --- Spike Simulation Parameters (Repeating) ---
spike_interval_minutes = 10 # How often the spike should occur (from start of one spike to start of the next)
spike_duration_minutes = 1  # How long each spike should last
spike_start_offset_minutes = 1 # How many minutes after the script starts the *first* spike should begin

# Convert spike parameters to seconds for calculations
spike_interval_seconds = spike_interval_minutes * 60
spike_duration_seconds = spike_duration_minutes * 60
spike_start_offset_seconds = spike_start_offset_minutes * 60

# --- Track script start time ---
script_start_time = time.monotonic() # Use monotonic time for reliable duration measurement


print(f"Starting live data generation for '{measurement_name}' on service '{service_name}'...")
print(f"Writing a point every {interval_seconds} seconds.")
print(f"Spike simulation parameters:")
print(f"  Interval between spikes: {spike_interval_minutes} minutes")
print(f"  Duration of each spike: {spike_duration_minutes} minute")
print(f"  First spike starts: {spike_start_offset_minutes} minutes after script start")


total_points_generated = 0
points_written_success = 0

try:
    # --- Generate and Write Data Continuously ---
    while True:
        current_monotonic_time = time.monotonic()
        time_since_script_start = current_monotonic_time - script_start_time
        current_datetime = datetime.now() # Get the current datetime for logging/timestamp clarity

        # Calculate the time into the current spike cycle, accounting for the initial offset
        # The cycle starts at `script_start_time + spike_start_offset_seconds`
        # We use modulo to wrap the time around the spike interval
        time_into_spike_cycle = (time_since_script_start - spike_start_offset_seconds) % spike_interval_seconds

        # Check if we are in the spike period
        # We are in a spike if time_into_spike_cycle is between 0 and spike_duration_seconds
        # Also, the first spike shouldn't start before spike_start_offset_seconds has passed
        is_in_spike = (time_since_script_start >= spike_start_offset_seconds) and \
                      (0 <= time_into_spike_cycle < spike_duration_seconds)


        # Determine latency based on whether we are in the spike period
        if is_in_spike:
            # Generate latency within the spike range
            latency_value = random.uniform(*spike_latency_range)
            latency_value = max(latency_value, normal_latency_range[1] + 10) # Ensure spike is above normal range
            print(f"{current_datetime.isoformat()}Z - Simulating spike: {latency_value:.2f}ms")
        else:
            # Generate latency within the normal range
            mean = (normal_latency_range[0] + normal_latency_range[1]) / 2
            std_dev = (normal_latency_range[1] - normal_latency_range[0]) / 6 # Rule of thumb: 6 std devs cover the range
            latency_value = random.gauss(mean, std_dev)
            latency_value = max(normal_latency_range[0], min(latency_value, normal_latency_range[1])) # Clamp to normal range
            print(f"{current_datetime.isoformat()}Z - Normal data: {latency_value:.2f}ms")


        # Create a Point object - DO NOT set a time here!
        # InfluxDB will assign the server's current timestamp automatically.
        point = Point(measurement_name) \
            .tag(key="service", value=service_name) \
            .tag(key="endpoint", value=endpoint_name) \
            .field(field="value", value=float(latency_value))

        # Write the individual point synchronously
        try:
            write_api.write(bucket=bucket, org=org, record=point)
            # print(f"  Wrote point successfully.") # Uncomment for verbose write confirmation
            points_written_success += 1
        except Exception as e:
            print(f"  ❌ Error writing point: {e}")

        total_points_generated += 1

        # Wait for the next interval
        time.sleep(interval_seconds)

except KeyboardInterrupt:
    # Handle Ctrl+C gracefully
    print("\nCtrl+C detected. Stopping.")

except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")


finally:
    # --- Cleanup ---
    print("\nCleaning up InfluxDB client resources...")
    try:
        if 'write_api' in locals() and write_api:
            write_api.close()
        if 'client' in locals() and client:
            client.close()
        print("InfluxDB client and write API closed.")
    except Exception as e:
         print(f"Error closing client or API: {e}")

    print(f"\nTotal points attempted to generate: {total_points_generated}")
    print(f"Total points written successfully: {points_written_success}")