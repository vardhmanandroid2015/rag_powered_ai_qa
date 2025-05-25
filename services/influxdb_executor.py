# rag_app/services/influxdb_executor.py

import os
import time
from datetime import datetime, timedelta, UTC
from influxdb_client import InfluxDBClient, HealthCheck
from influxdb_client.client.exceptions import InfluxDBError
import requests.exceptions
from dotenv import load_dotenv

# Attempt to load environment variables if not already loaded by the main app
load_dotenv()

# --- InfluxDB Configuration ---
# These should be defined in your config.py, loaded from environment variables.
# Ensure INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, and INFLUXDB_BUCKET are set.
# Assuming the bucket name for API latency data is system_services or similar.
# Make sure this matches your writer script's bucket.
try:
    from config import (
        INFLUXDB_URL,
        INFLUXDB_TOKEN,
        INFLUXDB_ORG,
        INFLUXDB_BUCKET, # Use the primary bucket from config
    )
except ImportError:
    print("❌ Could not import InfluxDB configuration from config.py.")
    print("   Ensure config.py exists and defines INFLUXDB_URL, TOKEN, ORG, BUCKET.")
    # Provide default values if config.py fails to import, for standalone testing capability
    INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN")
    INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG")
    INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "system_services")
    print(INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET)


# --- Client Initialization with Health Check and Retries ---
def get_influxdb_client():
    """
    Initializes and returns the InfluxDB client for querying.
    Performs a health check with retry logic.
    Returns client instance on success, None on permanent failure.
    """
    url = INFLUXDB_URL
    token = INFLUXDB_TOKEN
    org = INFLUXDB_ORG

    # --- Validate minimal configuration ---
    if not all([url, token, org]):
        print("❌ InfluxDB configuration (URL, TOKEN, or ORG) missing or incomplete.")
        print("   Ensure INFLUXDB_URL, INFLUXDB_TOKEN, and INFLUXDB_ORG are set in your environment or .env file.")
        return None

    # --- Set timeouts and retry parameters ---
    # Client timeout applies to connection and read operations for all client methods
    client_timeout_seconds = 60000 # Standard timeout for queries/health (e.g., 15-30 milliseconds)

    # Retry parameters for the initial health check only
    max_health_check_retries = 5 # Allow a few more retries for health check
    health_check_retry_delay_seconds = 3 # Wait a few seconds between health check retries


    client = None # Initialize client variable before the try block
    try:
        print(f"Attempting to initialize InfluxDB client for querying {url}, org {org} with timeout {client_timeout_seconds}s...")
        # Pass the timeout to the client constructor
        client = InfluxDBClient(url=url, token=token, org=org, timeout=client_timeout_seconds)
        print("✅ InfluxDB client initialized.")

        # --- Perform Health Check with Retry Logic ---
        attempt = 0
        health_check_passed = False
        last_health_status = None # Store status of the last attempt

        while attempt < max_health_check_retries:
            print(f"Performing InfluxDB health check (Attempt {attempt + 1}/{max_health_check_retries})...")
            try:
                # The health() method should respect the client's timeout
                last_health_status = client.health()

                print(f"DEBUG: InfluxDB Health Status (Attempt {attempt + 1}): {last_health_status.status}")
                if last_health_status.message:
                     print(f"DEBUG: InfluxDB Health Message (Attempt {attempt + 1}): {last_health_status.message}")
                if last_health_status.version:
                     print(f"DEBUG: InfluxDB Version (Attempt {attempt + 1}): {last_health_status.version}")
                if last_health_status.commit:
                     print(f"DEBUG: InfluxDB Commit (Attempt {attempt + 1}): {last_health_status.commit}")


                if last_health_status.status == "pass": # Explicitly check for "pass" string
                    print(f"✅ InfluxDB health check passed on attempt {attempt + 1}.")
                    health_check_passed = True
                    break # Exit retry loop on success
                else:
                    # Status is not 'pass', it's 'fail' or something unexpected
                    print(f"❌ InfluxDB health check failed on attempt {attempt + 1}. Status: {last_health_status.status}.")
                    attempt += 1
                    if attempt < max_health_check_retries:
                        print(f"Retrying health check in {health_check_retry_delay_seconds} seconds...")
                        time.sleep(health_check_retry_delay_seconds)
                    else:
                         print(f"❌ Max health check retries reached.")

            except requests.exceptions.Timeout as e:
                 # Catch timeouts specifically
                 print(f"❌ Health check Attempt {attempt + 1} timed out ({client_timeout_seconds}s timeout): {e}")
                 attempt += 1
                 if attempt < max_health_check_retries:
                    print(f"Retrying health check in {health_check_retry_delay_seconds} seconds...")
                    time.sleep(health_check_retry_delay_seconds)
                 else:
                     print(f"❌ Max health check retries reached due to timeout.")
            except InfluxDBError as e:
                 # Catch InfluxDB client specific errors (e.g., auth failed)
                 print(f"❌ Health check Attempt {attempt + 1} failed (InfluxDB Error): {e}")
                 attempt += 1
                 if attempt < max_health_check_retries:
                    print(f"Retrying health check in {health_check_retry_delay_seconds} seconds...")
                    time.sleep(health_check_retry_delay_seconds)
                 else:
                     print(f"❌ Max health check retries reached due to InfluxDB Error.")

            except Exception as e:
                 # Catch any other unexpected errors during the check attempt
                 print(f"❌ Health check Attempt {attempt + 1} failed (Unexpected Error): {type(e).__name__}: {e}")
                 attempt += 1
                 if attempt < max_health_check_retries:
                    print(f"Retrying health check in {health_check_retry_delay_seconds} seconds...")
                    time.sleep(health_check_retry_delay_seconds)
                 else:
                     print(f"❌ Max health check retries reached due to Unexpected Error.")


        # --- Final Status Check After Retries ---
        if health_check_passed:
             # If health check passed, return the client object
             # Optionally print individual check statuses if available in the final successful attempt
             if last_health_status and last_health_status.checks:
                 print("DEBUG: Individual Health Checks from successful attempt:")
                 for check in last_health_status.checks:
                     print(f"   - Check '{check.name}' Status: {check.status}, Message: {check.message}")
             return client

        else:
             # Health check failed after all retries
             print(f"❌ InfluxDB connection and health check permanently failed after {max_health_check_retries} attempts.")
             # last_health_status should hold the result of the last attempt if no exception occurred
             if last_health_status:
                  print(f"Last reported status: {last_health_status.status}. Message: {last_health_status.message}")
             # Ensure client is closed on permanent failure
             if client:
                 try:
                    client.close()
                    print("InfluxDB client closed after permanent health check failure.")
                 except Exception as close_e:
                    print(f"Error closing client after failure: {close_e}")
             return None # Indicate connection/health failure

    except Exception as e:
        # Catch any unexpected errors during client initialization itself (before the health check loop starts)
        print(f"❌ An unexpected error occurred during InfluxDB client initialization (before health check retry logic): {type(e).__name__}: {e}")
        if client: # If client was partially initialized before the error
             try:
                 client.close()
                 print("InfluxDB client closed after initialization error.")
             except Exception as close_e:
                 print(f"Error closing client after error: {close_e}")

        return None # Indicate a fundamental initialization error


# --- Execute Flux Query ---
def execute_flux_query(query: str):
    """
    Executes a Flux query against the configured bucket.
    Manages client connection internally per query execution.
    Returns a list of FluxTables on success, None on failure.
    """
    client = None # Initialize client to None before trying to get it
    try:
        # Get a client instance (this performs the health check and retries)
        client = get_influxdb_client()
        if client is None:
            print("❌ Failed to get InfluxDB client. Cannot execute query.")
            return None # get_influxdb_client already printed detailed error

        # Instantiate a query client from the connected client
        query_api = client.query_api()

        print(f"Executing InfluxDB query against bucket '{INFLUXDB_BUCKET}':\n---\n{query}\n---")
        # Execute the query, specifying the organization
        tables = query_api.query(query=query, org=INFLUXDB_ORG)

        print(f"✅ InfluxDB query executed successfully. Found {sum(len(table.records) for table in tables)} total data points across {len(tables)} tables.")

        return tables # Return the list of FluxTables

    except requests.exceptions.Timeout as e:
        # Catch timeouts during the query execution itself
        print(f"❌ InfluxDB query execution timed out: {e}")
        return None
    except InfluxDBError as e:
         # Catch InfluxDB client specific errors during query execution
         print(f"❌ InfluxDB Error during query execution: {e}")
         return None
    except Exception as e:
        # Catch any other unexpected errors during query execution
        print(f"❌ An unexpected error occurred during InfluxDB query execution: {type(e).__name__}: {e}")
        return None
    finally:
        # Ensure the client connection is closed after query execution
        # This is important because get_influxdb_client opens a new one.
        if client:
            try:
                client.close()
                print("✅ InfluxDB client closed after query execution.")
            except Exception as close_e:
                 print(f"Error closing client after query: {close_e}")


# --- Format Flux Results for LLM ---
def format_flux_tables_for_llm(tables):
    """
    Formats a list of FluxTables into a markdown-like string that's digestible by an LLM.
    Focuses on _time, _value, and relevant tags/fields.
    """
    if not tables or all(not table.records for table in tables):
        return "No relevant time-series data found."

    formatted_output = "--- InfluxDB Time-Series Data ---\n\n"

    for table in tables:
        # Get measurement, field, and result name from the first record if table has records
        if table.records:
            first_record = table.records[0]
            measurement = first_record.get_measurement() or 'Unknown Measurement'
            field = first_record.get_field() if first_record.get_field() is not None else 'Value' # Use 'Value' if field is None (e.g., from count())
            # Corrected: Access 'result' using .values.get() - This was already fixed
            result_name = first_record.values.get('result') or 'Query Result' # Get the 'result' column value

            # Construct a descriptive header for this table
            header_parts = [f"Measurement: '{measurement}'"]
            if field != 'Value': header_parts.append(f"Field: '{field}'")
            header_parts.append(f"Result: '{result_name}'")

            group_key = table.get_group_key()
            if group_key and hasattr(group_key, 'tags') and isinstance(getattr(group_key, 'tags', None), dict):
                 tag_parts = [f"{key}='{value}'" for key, value in group_key.tags.items()]
                 if tag_parts:
                      header_parts.append("Tags: " + ", ".join(tag_parts))


            formatted_output += " | ".join(header_parts) + "\n"
        else:
             formatted_output += "Empty Table\n" # Should be caught by the outer check, but safety


        # If the table has records, format them
        if table.records:
             # Get column labels dynamically from record values
             # This ensures we include all tags and fields present in the actual data
             example_record_keys = list(table.records[0].values.keys()) if table.records else []
             # Define a desired order for standard columns, include others dynamically
             header_cols = ["_time", "_value"]
             # Add other keys that are not the standard ones, excluding internal ones like _start, _stop, result, table
             relevant_tags_fields = [k for k in example_record_keys if k not in ["_time", "_value", "_start", "_stop", "_measurement", "_field", "result", "table"]]
             header_cols.extend(sorted(relevant_tags_fields)) # Add sorted relevant keys


             header_line = "| " + " | ".join(header_cols) + " |"
             separator_line = "|-" + "-|-".join(['-' * len(col) for col in header_cols]) + "-|"

             formatted_output += header_line + "\n"
             formatted_output += separator_line + "\n"


             # Sort records by time for better readability
             records = sorted(table.records, key=lambda r: r.get_time())

             for record in records:
                 row_data = []
                 # Get data for each column in our defined header_cols using record.values.get()
                 for col in header_cols:
                     # Use .values.get() for safe access to the underlying dictionary
                     value = record.values.get(col, 'N/A') # Use 'N/A' if key is missing

                     # Special formatting for _time and _value if needed
                     if col == "_time":
                          row_data.append(str(record.get_time())) # Use get_time() for datetime object
                     elif col == "_value":
                          # Format _value to 2 decimal places for metrics, or keep as string if not numeric
                          try:
                              row_data.append(f"{value:.2f}" if isinstance(value, (int, float)) else str(value))
                          except (ValueError, TypeError):
                               # Handle cases where value isn't a number for formatting
                               row_data.append(str(value))
                     else:
                          # For other tags/fields, just convert to string
                          row_data.append(str(value))

                 formatted_output += "| " + " | ".join(row_data) + " |\n"

             formatted_output += "\n" # Add newline after each table data section

    formatted_output += "--------------------------\n"
    return formatted_output


# --- Example Usage (for testing this script directly) ---
# This block allows you to run this file independently to test the InfluxDB connection,
# health check, and basic querying/formatting without the full RAG app.
if __name__ == "__main__":
    print("--- Running influxdb_executor.py standalone test ---")

    # Load env vars again just in case for standalone run
    load_dotenv()

    # --- Define an Example Flux Query ---
    # This query should retrieve recent data from the bucket where your writer script is sending api_latency data.
    # Adjust the bucket name and time range as needed to match your data.
    test_bucket_name = os.environ.get("INFLUXDB_BUCKET", "system_services") # Use bucket from env/config, default if not set

    # Use a query that yields some data, like fetching raw points or a basic aggregation
    # This query should match the structure that caused the error
    test_query = f'''
    from(bucket: "{test_bucket_name}")
      |> range(start: -1m) // Get data from the last 5 minutes (adjust if needed)
      |> filter(fn: (r) => r._measurement == "api_latency")
      |> filter(fn: (r) => r.service == "payment" and r.endpoint == "/process")
      |> filter(fn: (r) => r._field == "value")
      |> yield(name: "recent_payment_latency")
    '''
    # You can uncomment the aggregateWindow line to test the grouping case too:
    # test_query_agg = f'''
    # from(bucket: "{test_bucket_name}")
    #   |> range(start: -15m)
    #   |> filter(fn: (r) => r._measurement == "api_latency")
    #   |> filter(fn: (r) => r.service == "payment" and r.endpoint == "/process")
    #   |> filter(fn: (r) => r._field == "value")
    #   |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
    #   |> yield(name: "aggregated_payment_latency")
    # '''


    print("\n--- Executing example query via execute_flux_query ---")
    query_results = execute_flux_query(test_query) # Use test_query, not test_query_agg initially to replicate error

    print(query_results[0].records[0])

    print("\n--- Formatting results for LLM ---")
    formatted_output = format_flux_tables_for_llm(query_results)

    print("\n--- Final Formatted Output ---")
    print(formatted_output)
    print("-----------------------------")
